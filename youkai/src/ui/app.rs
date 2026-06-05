use std::fmt::Display;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::PathBuf;
use std::thread;
use std::time::Instant;

use anyhow::{Context as _, Result, anyhow};
use chrono::Local;
use egui::{
    Button, Color32, Context, DragValue, Id, Key, KeyboardShortcut, Modal, Modifiers, OpenUrl,
    PointerButton, RichText, Sense, ViewportCommand,
};
use egui_file_dialog::FileDialog;
use egui_notify::Toasts;
use serde::{Deserialize, Serialize};
use tokio::sync::{mpsc, oneshot, watch};

use crate::monitor::Monitor;
use crate::player_data::ExportSettings;
use crate::update::check_for_app_update;
use crate::{
    AppState, ConfirmationType, Message, ReloadHandle, State, TracingLevel, open_log_dir, wish,
};

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SavedAppState {
    export_settings: ExportSettings,
    #[serde(default)]
    auto_start_capture: bool,
    log_raw_packets: bool,
    #[serde(default)]
    tracing_level: TracingLevel,
    #[serde(default)]
    capture_all_udp: bool,
}

impl Default for SavedAppState {
    fn default() -> Self {
        Self {
            export_settings: ExportSettings {
                include_characters: true,
                include_artifacts: true,
                include_weapons: true,
                include_materials: true,
                fake_initialize_4th_line: false,
                min_character_level: 1,
                min_character_ascension: 0,
                min_character_constellation: 0,
                min_artifact_level: 0,
                min_artifact_rarity: 5,
                min_weapon_level: 1,
                min_weapon_refinement: 0,
                min_weapon_ascension: 0,
                min_weapon_rarity: 3,
            },
            auto_start_capture: false,
            log_raw_packets: false,
            tracing_level: Default::default(),
            capture_all_udp: false,
        }
    }
}

#[derive(Clone, Debug)]
enum OptimizerExportTarget {
    None,
    Clipboard,
    File,
}

pub struct YoukaiApp {
    ui_message_tx: mpsc::UnboundedSender<Message>,
    state_rx: watch::Receiver<AppState>,
    wish_url_rx: watch::Receiver<Option<String>>,
    log_packets_tx: watch::Sender<bool>,
    tracing_reload_handle: ReloadHandle,

    toasts: Toasts,

    power_tools_open: bool,
    bug_report_open: bool,

    capture_settings_open: bool,

    // ZZZ Exporter additions
    zzz_settings_open: bool,
    zzz_export_rx: Option<oneshot::Receiver<Result<String>>>,
    zzz_save_dialog: Option<FileDialog>,
    zzz_save_path: Option<PathBuf>,
    zzz_export_target: OptimizerExportTarget,
    zzz_export_include_characters: bool,

    restarting: bool,

    saved_state: SavedAppState,

    interknot_packets: u32,
    tops_packets: u32,
    last_packet_tick: std::time::Instant,
}

trait ToastError<T> {
    fn toast_error(self, app: &mut YoukaiApp) -> Option<T>;
}

impl<T, E: Display> ToastError<T> for std::result::Result<T, E> {
    fn toast_error(self, app: &mut YoukaiApp) -> Option<T> {
        match self {
            Ok(val) => Some(val),
            Err(e) => {
                tracing::error!("{e}");
                app.toasts.error(e.to_string());
                None
            }
        }
    }
}

fn start_async_runtime(
    egui_ctx: Context,
    log_packets_rx: watch::Receiver<bool>,
) -> (
    mpsc::UnboundedSender<Message>,
    watch::Receiver<AppState>,
    watch::Receiver<Option<String>>,
) {
    tracing::info!("starting tokio async");
    let (ui_message_tx, mut ui_message_rx) = mpsc::unbounded_channel::<Message>();

    let (state_tx, state_rx) = watch::channel(AppState::new());
    let (wish_url_tx, wish_url_rx) = watch::channel(None);
    let mut updater_state_rx = state_rx.clone();
    let updater_ctx = egui_ctx.clone();
    thread::spawn(move || {
        let rt = tokio::runtime::Runtime::new().unwrap();

        rt.block_on(async {
            // Before starting the monitor, check for updates if not in debug mode
            tracing::info!("Checking for update");
            if let Err(e) = check_for_app_update(&state_tx, &mut ui_message_rx).await {
                tracing::error!("error checking for update: {e}");
            }

            // Check for wish URL
            tokio::spawn(async move {
                let Ok(mut wish) = wish::Wish::new(wish_url_tx).await else {
                    tracing::error!("Failed to create new wish monitor");
                    return;
                };

                if let Err(e) = wish.monitor().await {
                    tracing::error!("Error monitoring for wishes: {e}");
                }
            });

            // Notify egui of state changes.
            tokio::spawn(async move {
                loop {
                    let _ = updater_state_rx.changed().await;
                    updater_ctx.request_repaint();
                }
            });
            tracing::info!("Starting monitor");
            let monitor = match Monitor::new(state_tx, ui_message_rx, log_packets_rx).await {
                Ok(monitor) => monitor,
                Err(e) => {
                    tracing::error!("error loading monitor task: {e}");
                    return;
                }
            };
            monitor.run().await;
        });
    });
    tracing::info!("started tokio");
    (ui_message_tx, state_rx, wish_url_rx)
}

impl YoukaiApp {
    pub fn new(cc: &eframe::CreationContext<'_>, mut tracing_reload_handle: ReloadHandle, capture_all_udp: bool) -> Self {
        egui_extras::install_image_loaders(&cc.egui_ctx);
        egui_material_icons::initialize(&cc.egui_ctx);

        cc.egui_ctx.style_mut(|style| {
            // Retro 1990s blocky rounding (no curved borders)
            style.visuals.window_corner_radius = egui::CornerRadius::ZERO;
            style.visuals.widgets.noninteractive.corner_radius = egui::CornerRadius::ZERO;
            style.visuals.widgets.inactive.corner_radius = egui::CornerRadius::ZERO;
            style.visuals.widgets.hovered.corner_radius = egui::CornerRadius::ZERO;
            style.visuals.widgets.active.corner_radius = egui::CornerRadius::ZERO;
            style.visuals.widgets.open.corner_radius = egui::CornerRadius::ZERO;

            style.visuals.dark_mode = true;
            
            let bg_color = Color32::from_rgb(0x00, 0x00, 0x00); // Black screen
            let widget_inactive_bg = Color32::from_rgb(0x0c, 0x06, 0x12); // Extremely dark purple-black
            let widget_hovered_bg = Color32::from_rgb(0xff, 0x00, 0x90); // Youkai Neon Magenta
            let widget_active_bg = Color32::from_rgb(0xc2, 0x00, 0x6d); // Clicked state
            
            let text_color_light = Color32::from_rgb(0xfd, 0xf5, 0xfa);
            let text_color_dark = Color32::from_rgb(0x00, 0x00, 0x00);
            
            style.visuals.override_text_color = Some(text_color_light);
            style.visuals.window_fill = bg_color;
            style.visuals.panel_fill = bg_color;
            
            // Inactive buttons / widgets
            style.visuals.widgets.inactive.bg_fill = widget_inactive_bg;
            style.visuals.widgets.inactive.fg_stroke = egui::Stroke::new(1.5_f32, Color32::from_rgb(0xa8, 0x2b, 0x72));
            style.visuals.widgets.inactive.weak_bg_fill = widget_inactive_bg;
            
            // Hovered buttons / widgets (glow neon magenta and change text to black)
            style.visuals.widgets.hovered.bg_fill = widget_hovered_bg;
            style.visuals.widgets.hovered.fg_stroke = egui::Stroke::new(2.0_f32, text_color_dark);
            style.visuals.widgets.hovered.weak_bg_fill = widget_hovered_bg;
            
            // Active (clicked) buttons / widgets
            style.visuals.widgets.active.bg_fill = widget_active_bg;
            style.visuals.widgets.active.fg_stroke = egui::Stroke::new(2.0_f32, text_color_dark);
            style.visuals.widgets.active.weak_bg_fill = widget_active_bg;
            
            // Noninteractive elements (layout lines, border separators)
            style.visuals.widgets.noninteractive.bg_fill = bg_color;
            style.visuals.widgets.noninteractive.fg_stroke = egui::Stroke::new(1.0_f32, Color32::from_rgb(0x4d, 0x15, 0x38));
            
            // Re-map text styles to Monospace for that retro CLI computer aesthetic
            for font_id in style.text_styles.values_mut() {
                font_id.family = egui::FontFamily::Monospace;
            }
        });


        let mut saved_state: SavedAppState = if let Some(storage) = cc.storage {
            eframe::get_value(storage, eframe::APP_KEY).unwrap_or_default()
        } else {
            Default::default()
        };

        if capture_all_udp {
            saved_state.capture_all_udp = true;
        }

        tracing_reload_handle.set_filter(saved_state.tracing_level.get_filter());
        let (log_packets_tx, log_packets_rx) = watch::channel(saved_state.log_raw_packets);
        let (ui_message_tx, state_rx, wish_url_rx) =
            start_async_runtime(cc.egui_ctx.clone(), log_packets_rx);

        if saved_state.auto_start_capture {
            if let Err(e) = ui_message_tx.send(Message::StartCapture(saved_state.capture_all_udp)) {
                tracing::error!("Failed to send auto start message: {e}");
            }
        }

        let toasts = Toasts::default().with_anchor(egui_notify::Anchor::BottomLeft);

        Self {
            saved_state,
            ui_message_tx,
            log_packets_tx,
            tracing_reload_handle,
            toasts,
            power_tools_open: false,
            bug_report_open: false,
            capture_settings_open: false,
            zzz_settings_open: false,
            zzz_export_rx: None,
            zzz_save_dialog: None,
            zzz_save_path: None,
            zzz_export_target: OptimizerExportTarget::None,
            zzz_export_include_characters: false,
            restarting: false,
            state_rx,
            wish_url_rx,
            interknot_packets: 0,
            tops_packets: 0,
            last_packet_tick: std::time::Instant::now(),
        }
    }
}

impl eframe::App for YoukaiApp {
    /// Called by the framework to save state before shutdown.
    fn save(&mut self, storage: &mut dyn eframe::Storage) {
        eframe::set_value(storage, eframe::APP_KEY, &self.saved_state);
    }

    /// Called each time the UI needs repainting, which may be many times per second.
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        let mut clicked_exit = false;
        ctx.style_mut(|style| {
            style.interaction.selectable_labels = false;
            style.interaction.tooltip_delay = 0.25;
        });

        self.toasts.show(ctx);
        if let Some(zzz_save_dialog) = &mut self.zzz_save_dialog {
            zzz_save_dialog.update(ctx);
        }

        egui::CentralPanel::default().show(ctx, |ui| {
            let rect = ui.max_rect();
            {
                // Fill background with solid black
                ui.painter().rect_filled(rect, egui::Rounding::ZERO, Color32::from_rgb(0, 0, 0));
            }

            ui.vertical(|ui| {
                clicked_exit = self.title_bar(ui);
                ui.add_space(10.);

                // Handle power tools here instead of main UI to allow it to be opened
                // in other app states.
                let power_tools_shortcut = KeyboardShortcut {
                    modifiers: Modifiers {
                        command: true,
                        shift: true,
                        ..Default::default()
                    },
                    logical_key: Key::P,
                };
                ui.ctx().input_mut(|i| {
                    if i.consume_shortcut(&power_tools_shortcut) {
                        self.power_tools_open = true;
                    }
                });

                if self.power_tools_open {
                    let modal = Modal::new(Id::new("Power Tools")).show(ui.ctx(), |ui| {
                        self.power_tools_modal(ui);
                    });
                    if modal.should_close() {
                        self.power_tools_open = false;
                    }
                }

                if self.bug_report_open {
                    let modal = Modal::new(Id::new("Bug Report")).show(ui.ctx(), |ui| {
                        self.bug_report_modal(ui);
                    });
                    if modal.should_close() {
                        self.bug_report_open = false;
                    }
                }

                // Draw Grid_OS double-line window frame
                let window_rect = rect.shrink2(egui::vec2(20.0, 40.0)); // 20px padding left/right, 40px top/bottom
                let frame_stroke_outer = egui::Stroke::new(1.5_f32, Color32::from_rgb(0xff, 0x00, 0x90));
                let frame_stroke_inner = egui::Stroke::new(0.8_f32, Color32::from_rgb(0xff, 0x00, 0x90));
                
                ui.painter().rect_stroke(window_rect, egui::Rounding::ZERO, frame_stroke_outer, egui::StrokeKind::Inside);
                ui.painter().rect_stroke(window_rect.shrink(3.0_f32), egui::Rounding::ZERO, frame_stroke_inner, egui::StrokeKind::Inside);

                // Place contents inside Grid_OS window frame
                ui.allocate_ui_at_rect(window_rect.shrink(8.0), |ui| {
                    ui.vertical(|ui| {
                        // Window Header
                        ui.horizontal(|ui| {
                            ui.label(
                                RichText::new("// SYSTEM STATUS // YOUKAI_GRID_OS v9.4")
                                    .color(Color32::from_rgb(0xff, 0x00, 0x90))
                                    .strong()
                                    .size(11.0)
                            );
                        });
                        ui.separator();
                        ui.add_space(8.0);

                        let state = self.state_rx.borrow_and_update().clone();

                        // Increment counters if capturing
                        if state.capturing {
                            let now = std::time::Instant::now();
                            if now.duration_since(self.last_packet_tick) > std::time::Duration::from_millis(150) {
                                let ticks = now.elapsed().subsec_nanos();
                                self.interknot_packets += (ticks % 3) + 1;
                                self.tops_packets += (ticks % 2) + 1;
                                self.last_packet_tick = now;
                            }
                        } else {
                            self.interknot_packets = 0;
                            self.tops_packets = 0;
                        }

                        // Check if running as administrator
                        if !crate::ui::admin::is_admin() {
                            egui::Frame::group(ui.style())
                                .fill(Color32::from_rgb(0x2d, 0x12, 0x12)) // Dark crimson
                                .stroke(egui::Stroke::new(1.5_f32, Color32::from_rgb(0xff, 0x00, 0x55)))
                                .inner_margin(8.0)
                                .show(ui, |ui| {
                                    ui.vertical(|ui| {
                                        ui.label(
                                            RichText::new("⚠️ INTRUSION FAILURE")
                                                .color(Color32::from_rgb(0xff, 0x00, 0x55))
                                                .strong()
                                                .size(13.0)
                                        );
                                        ui.add_space(4.0);
                                        ui.label(
                                            RichText::new("You think you can sniff packets without admin rights? Expose your Administrator credentials (Run as Admin) or my sniffer stays offline!")
                                                .size(11.0)
                                        );
                                    });
                                });
                            ui.add_space(10.0);
                        }

                        match state.state {
                            State::Starting => (),
                            State::CheckingForUpdate => self.checking_for_update_ui(ui),
                            State::WaitingForUpdateConfirmation(status) => {
                                self.waiting_for_update_confirmation_ui(ui, status)
                            }
                            State::Updating => self.updating_ui(ui),
                            State::Updated => self.updated_ui(ui),
                            State::CheckingForData => self.checking_for_data_ui(ui),
                            State::WaitingForDownloadConfirmation(confirmation_type) => {
                                self.waiting_for_download_confirmation_ui(ui, confirmation_type)
                            }
                            State::Downloading => self.load_data_ui(ui),
                            State::Main => self.main_ui(ui, &state),
                        }
                    });
                });
            });

            // Outer Screen Footer - clean version indicator only
            ui.with_layout(egui::Layout::bottom_up(egui::Align::RIGHT), |ui| {
                ui.horizontal(|ui| {
                    ui.label(RichText::new(format!("v{}", env!("CARGO_PKG_VERSION"))).color(Color32::from_rgb(0xa8, 0x2b, 0x72)).size(8.0));
                    egui::warn_if_debug_build(ui);
                });
            });
        });

        if clicked_exit {
            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
        }
    }
}

impl YoukaiApp {
    fn title_bar(&mut self, ui: &mut egui::Ui) -> bool {
        let clock_str = chrono::Local::now().format("%Y.%m.%d // %H:%M:%S %Z").to_string();
        let mut clicked_exit = false;
        
        let (_, _button_width) = egui::Sides::new().show(
            ui,
            |ui| {
                ui.horizontal(|ui| {
                    ui.add_space(8.0);
                    // Draw a mini Youkai icon in the title bar
                    let logo = egui::Image::new(egui::include_image!("../../assets/icon-256.png"))
                        .max_width(20.0_f32)
                        .max_height(20.0_f32);
                    ui.add(logo);
                });
            },
            |ui| {
                ui.horizontal(|ui| {
                    // Ticking clock
                    ui.label(
                        RichText::new(clock_str)
                            .monospace()
                            .color(Color32::from_rgb(0xff, 0x00, 0x90))
                            .size(11.0_f32)
                    );
                    ui.add_space(10.0_f32);
                    
                    // Exit button
                    let button = ui.add(
                        Button::new(
                            RichText::new(" EXIT ")
                                .strong()
                                .monospace()
                                .color(Color32::from_rgb(0, 0, 0))
                        )
                        .fill(Color32::from_rgb(0xff, 0x00, 0x55)) // Neon Pink-Red
                        .stroke(egui::Stroke::new(1.0_f32, Color32::from_rgb(0xff, 0x00, 0x55)))
                    );
                    if button.clicked() {
                        clicked_exit = true;
                        ui.ctx().send_viewport_cmd(egui::ViewportCommand::Close);
                    }
                    button.rect.width()
                }).inner
            },
        );

        let app_rect = ui.max_rect();

        let title_bar_height = 32.0_f32;
        let title_bar_rect = {
            let mut rect = app_rect;
            rect.max.y = rect.min.y + title_bar_height;
            rect.max.x = rect.min.x + 480.0_f32; // Limit drag region to 480px from left to avoid clock/exit button overlap
            rect
        };

        let response = ui.interact(
            title_bar_rect,
            Id::new("title_bar"),
            Sense::click_and_drag(),
        );

        if response.drag_started_by(PointerButton::Primary) {
            ui.ctx().send_viewport_cmd(ViewportCommand::StartDrag);
        }
        
        clicked_exit
    }

    fn checking_for_update_ui(&self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            ui.label("Prying into the mainframe for updates... Don't touch anything.".to_string());
        });
    }

    fn waiting_for_update_confirmation_ui(&self, ui: &mut egui::Ui, version: String) {
        ui.label(format!(
            "Detected version {}. A shiny new chassis is waiting. Shall we hijack the server and download it?",
            version
        ));

        ui.horizontal(|ui| {
            if ui.add(egui::Button::new("Inject Update")).clicked() {
                if let Err(e) = self.ui_message_tx.send(Message::UpdateAcknowledged) {
                    tracing::error!("Unable to send UI message: {e}");
                }
            }
            if ui.add(egui::Button::new("Stay Outdated")).clicked() {
                if let Err(e) = self.ui_message_tx.send(Message::UpdateCanceled) {
                    tracing::error!("Unable to send UI message: {e}");
                }
            }
        });
    }

    fn updating_ui(&self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            ui.label("Injecting updates into my core... Hold your horses, human.".to_string());
            ui.spinner();
        });
    }

    fn updated_ui(&mut self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            ui.label("Core system upgraded. Re-infiltrating in 3... 2... 1...".to_string());
        });
        if !self.restarting {
            let program_name = std::env::args().next().unwrap();
            let _ = std::process::Command::new(program_name).spawn();
            ui.ctx().send_viewport_cmd(egui::ViewportCommand::Close);
            self.restarting = true;
        }
    }

    fn checking_for_data_ui(&self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            ui.label("Scanning Hoyoverse databases for changes. Stay alert...".to_string());
        });
    }

    fn waiting_for_download_confirmation_ui(
        &self,
        ui: &mut egui::Ui,
        confirmation_type: ConfirmationType,
    ) {
        let label = match confirmation_type {
            ConfirmationType::Initial => "My memory banks are empty. Let me leech the initial game data, human.",
            ConfirmationType::Update => "New data identified. Authorize the siphon?",
        };
        ui.label(label.to_string());
        if ui.add(egui::Button::new("Siphon Data")).clicked() {
            if let Err(e) = self.ui_message_tx.send(Message::DownloadAcknowledged) {
                tracing::error!("Unable to send UI message{e}");
            }
        }
    }

    fn load_data_ui(&self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            ui.label("Siphoning game files... Decoding packages...".to_string());
            ui.spinner();
        });
    }

    fn main_ui(&mut self, ui: &mut egui::Ui, app_state: &AppState) {
        if self.capture_settings_open {
            let modal = Modal::new(Id::new("Capture Settings")).show(ui.ctx(), |ui| {
                self.capture_settings_modal(ui);
            });
            if modal.should_close() {
                self.capture_settings_open = false;
            }
        }

        ui.horizontal(|ui| {
            // LEFT COLUMN: Terminal Logs & Signal Intrusion
            ui.vertical(|ui| {
                ui.set_width(350.0_f32);
                
                ui.label(
                    RichText::new("// ACTIVE INTRUSION PIPELINE")
                        .color(Color32::from_rgb(0xff, 0x00, 0x90))
                        .strong()
                        .size(11.0_f32)
                );
                ui.add_space(4.0_f32);

                // Terminal Box Frame (stretches to remaining height)
                let terminal_height = ui.available_height() - 6.0_f32;
                egui::Frame::canvas(ui.style())
                    .fill(Color32::from_rgb(0x07, 0x03, 0x0b))
                    .stroke(egui::Stroke::new(1.0_f32, Color32::from_rgb(0x3d, 0x0f, 0x28)))
                    .inner_margin(12.0_f32)
                    .show(ui, |ui| {
                        ui.set_height(terminal_height);
                        ui.vertical(|ui| {
                            ui.label(
                                RichText::new("YOUKAI // INT_CMD_LINE")
                                    .color(Color32::from_rgb(0xff, 0x00, 0x90))
                                    .strong()
                                    .size(10.0_f32)
                            );
                            ui.separator();
                            ui.add_space(4.0_f32);

                            // Connection Logs
                            let conn_status = if app_state.capturing { "INTRUDING" } else { "STANDBY" };
                            let conn_color = if app_state.capturing { Color32::from_rgb(0xff, 0x00, 0x90) } else { Color32::from_rgb(0x80, 0x85, 0x90) };
                            
                            ui.label(
                                RichText::new(format!("TUNNEL STATUS : [{}]", conn_status))
                                    .color(conn_color)
                                    .monospace()
                                    .size(10.0_f32)
                            );
                            
                            ui.label(
                                RichText::new("TARGET        : [ INTER-KNOT BACKEND DATABASE ]")
                                    .color(Color32::from_rgb(0xff, 0xf0, 0xf8))
                                    .monospace()
                                    .size(10.0_f32)
                            );
                            
                            // More room between status text and progress bar/packet stream
                            ui.add_space(24.0_f32);

                            // Youkai Dialogue Text
                            let dialogue = if app_state.capturing {
                                "Packet stream intercepted. Extracting combat signatures... Keep the client active, human."
                            } else {
                                "Intrusion system idle. Give the order (EXECUTE EXTRACTION SCRIPT) to begin the network hijack."
                            };
                            
                            ui.label(
                                RichText::new(dialogue)
                                    .color(Color32::from_rgb(0xa8, 0x2b, 0x72))
                                    .size(10.0_f32)
                            );
                            
                            // Align Status and Telemetry to the bottom of the left column
                            ui.with_layout(egui::Layout::bottom_up(egui::Align::Min), |ui| {
                                ui.vertical(|ui| {
                                    // Animated Loading/Progress Bar (Status Bar)
                                    let progress_bar = if app_state.capturing {
                                        let ticks = (ui.input(|i| i.time * 4.0) as usize) % 11;
                                        let bar: String = (0..10).map(|j| if j < ticks { "■" } else { " " }).collect();
                                        format!("[{}]", bar)
                                    } else {
                                        "[          ]".to_string()
                                    };
                                    
                                    ui.label(
                                        RichText::new(progress_bar)
                                            .color(Color32::from_rgb(0xff, 0x00, 0x90))
                                            .monospace()
                                            .strong()
                                    );

                                    ui.add_space(8.0_f32);

                                    // Three Status lines
                                    self.terminal_stat_row(ui, "Drive Discs Cracked", app_state.updated.items_updated);
                                    self.terminal_stat_row(ui, "Agent Accounts Hacked", app_state.updated.characters_updated);
                                    
                                    let compile_complete = app_state.updated.items_updated.is_some() && app_state.updated.characters_updated.is_some();
                                    let compile_str = if compile_complete { "COMPLETE" } else { "INCOMPLETE" };
                                    let compile_color = if compile_complete { Color32::from_rgb(0xff, 0x00, 0x90) } else { Color32::from_rgb(0x80, 0x85, 0x90) };
                                    ui.label(
                                        RichText::new(format!("Extracted data compiled: [{}]", compile_str))
                                            .color(compile_color)
                                            .monospace()
                                            .size(10.0_f32)
                                    );

                                    ui.add_space(8.0_f32);

                                    // Telemetry packet counters
                                    ui.horizontal(|ui| {
                                        ui.label(
                                            RichText::new("INTER-KNOT API PACKETS CAPTURED:")
                                                .color(Color32::from_rgb(0xff, 0xf0, 0xf8))
                                                .size(8.0_f32)
                                        );
                                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                            ui.label(
                                                RichText::new(format!("{}", self.interknot_packets))
                                                    .color(Color32::from_rgb(0xff, 0x00, 0x90))
                                                    .monospace()
                                                    .strong()
                                                    .size(8.0_f32)
                                            );
                                        });
                                    });
                                    
                                    ui.horizontal(|ui| {
                                        ui.label(
                                            RichText::new("TOPS DATA INTERCEPTED:")
                                                .color(Color32::from_rgb(0xff, 0xf0, 0xf8))
                                                .size(8.0_f32)
                                        );
                                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                            ui.label(
                                                RichText::new(format!("{}", self.tops_packets))
                                                    .color(Color32::from_rgb(0xff, 0x00, 0x90))
                                                    .monospace()
                                                    .strong()
                                                    .size(8.0_f32)
                                            );
                                        });
                                    });

                                    ui.add_space(6.0_f32);

                                    // Oscilloscope waveform segment
                                    let speed = if app_state.capturing { 8.0_f32 } else { 0.0_f32 };
                                    let amplitude_multiplier = if app_state.capturing { 1.0_f32 } else { 0.0_f32 };
                                    self.draw_waveform(ui, Color32::from_rgb(0xff, 0x00, 0x90), 24.0_f32, speed, amplitude_multiplier);

                                    ui.add_space(8.0_f32);

                                    // Control Buttons (Renamed to Extraction Script terminology)
                                    ui.horizontal(|ui| {
                                        if app_state.capturing {
                                            if ui.button(" KILL EXTRACTION SCRIPT ").clicked() {
                                                let _ = self.ui_message_tx.send(Message::StopCapture);
                                            }
                                        } else {
                                            if ui.button(" EXECUTE EXTRACTION SCRIPT ").clicked() {
                                                let _ = self.ui_message_tx.send(Message::StartCapture(self.saved_state.capture_all_udp));
                                            }
                                        }
                                    });
                                });
                            });
                        });
                    });
            });

            ui.add_space(16.0_f32);

            // RIGHT COLUMN: Tactical Map & Inter-Knot Exporter Parameters
            ui.vertical(|ui| {
                let right_width = ui.available_width() - 6.0_f32;
                ui.set_width(right_width);

                // Map Display Box (Upper Right) - extended to right edge
                let map_height = 180.0_f32;
                egui::Frame::canvas(ui.style())
                    .fill(Color32::from_rgb(0, 0, 0))
                    .stroke(egui::Stroke::new(1.0_f32, Color32::from_rgb(0x4d, 0x15, 0x38)))
                    .inner_margin(0.0_f32)
                    .show(ui, |ui| {
                        let map_image = egui::Image::new(egui::include_image!("../../assets/map.webp"))
                            .max_height(map_height)
                            .max_width(right_width);
                        let response = ui.add(map_image);
                        let rect = response.rect;
                        
                        // Draw custom vector HUD crosshair and "TARGET ACQUIRED" text on top of the map
                        let painter = ui.painter();
                        let center = egui::pos2(rect.min.x + rect.width() * 0.64, rect.center().y);
                        let color = Color32::from_rgb(0xff, 0x00, 0x90);
                        
                        // 1. Draw outer circle
                        painter.circle_stroke(center, 13.0, egui::Stroke::new(1.6_f32, color));
                        
                        // 2. Draw inner center dot
                        painter.circle_filled(center, 2.2, color);
                        
                        // 3. Draw 4 crosshair lines
                        painter.line_segment([center - egui::vec2(0.0, 24.0), center - egui::vec2(0.0, 13.0)], egui::Stroke::new(1.6_f32, color));
                        painter.line_segment([center + egui::vec2(0.0, 13.0), center + egui::vec2(0.0, 24.0)], egui::Stroke::new(1.6_f32, color));
                        painter.line_segment([center - egui::vec2(24.0, 0.0), center - egui::vec2(13.0, 0.0)], egui::Stroke::new(1.6_f32, color));
                        painter.line_segment([center + egui::vec2(13.0, 0.0), center + egui::vec2(24.0, 0.0)], egui::Stroke::new(1.6_f32, color));
                        
                        // 4. Draw TARGET ACQUIRED text next to the crosshair
                        let text_pos = center + egui::vec2(22.0, -16.0);
                        painter.text(
                            text_pos,
                            egui::Align2::LEFT_TOP,
                            "TARGET\nACQUIRED",
                            egui::FontId::new(16.0_f32, egui::FontFamily::Monospace),
                            color
                        );
                    });

                ui.add_space(8.0_f32);

                // Inter-Knot Decrypter Parameters (Lower Right)
                let decrypter_box_height = ui.available_height() - 6.0_f32;
                egui::Frame::canvas(ui.style())
                    .fill(Color32::from_rgb(0x07, 0x03, 0x0b))
                    .stroke(egui::Stroke::new(1.0_f32, Color32::from_rgb(0x3d, 0x0f, 0x28)))
                    .inner_margin(8.0_f32)
                    .show(ui, |ui| {
                        ui.set_height(decrypter_box_height);
                        ui.vertical(|ui| {
                            ui.label(
                                RichText::new("// INTER-KNOT DECRYPTER PARAMETERS")
                                    .color(Color32::from_rgb(0xff, 0x00, 0x90))
                                    .strong()
                                    .size(10.0_f32)
                            );
                            ui.separator();
                            ui.add_space(4.0_f32);

                            // Configuration button placed directly under the header
                            ui.horizontal(|ui| {
                                if ui.button(" Configuration ").clicked() {
                                    self.capture_settings_open = true;
                                }
                            });
                            ui.add_space(8.0_f32);

                            // Inline parameters (Toggles for Agents and Discs)
                            ui.horizontal(|ui| {
                                ui.checkbox(
                                    &mut self.saved_state.export_settings.include_characters,
                                    RichText::new("Agent Combat Data").size(9.0_f32)
                                );
                                ui.add_space(8.0_f32);
                                ui.checkbox(
                                    &mut self.saved_state.export_settings.include_artifacts,
                                    RichText::new("Drive Disc Partitions").size(9.0_f32)
                                );
                            });

                            ui.add_space(6.0_f32);

                            // Copy Clipboard / Export buttons
                            let compile_complete = app_state.updated.items_updated.is_some() && app_state.updated.characters_updated.is_some();
                            self.zenless_optimizer_handle_export(ui).toast_error(self);

                            if let Some(zzz_save_dialog) = &mut self.zzz_save_dialog
                                && let Some(path) = zzz_save_dialog.take_picked()
                            {
                                self.zzz_save_path = Some(path);
                                self.zenless_optimizer_request_export(OptimizerExportTarget::File, true);
                            }

                            if compile_complete {
                                ui.horizontal(|ui| {
                                    ui.add_enabled_ui(self.zzz_export_rx.is_none(), |ui| {
                                        if ui.button(RichText::new(" COPY CLIPBOARD ").size(9.0_f32)).clicked() {
                                            self.zenless_optimizer_request_export(OptimizerExportTarget::Clipboard, true);
                                        }
                                        ui.add_space(8.0_f32);
                                        if ui.button(RichText::new(" EXPORT FILE ").size(9.0_f32)).clicked() {
                                            let now = Local::now();
                                            let mut zzz_save_dialog = FileDialog::new()
                                                .add_file_filter_extensions("JSON files", vec!["json"])
                                                .default_file_name(&format!(
                                                    "youkai_export_{}.json",
                                                    now.format("%Y-%m-%d_%H-%M")
                                                ));
                                            zzz_save_dialog.save_file();
                                            self.zzz_save_dialog = Some(zzz_save_dialog);
                                            self.zzz_export_target = OptimizerExportTarget::File;
                                            self.zzz_export_include_characters = true;
                                        }
                                    });
                                });
                            } else {
                                ui.label(
                                    RichText::new("[ INTRUSION INCOMPLETE - SIPHONING GAME RECORDS... ]")
                                        .color(Color32::from_rgb(0xa8, 0x2b, 0x72))
                                        .monospace()
                                        .size(9.0_f32)
                                );
                            }
                        });
                    });
            });
        });
    }

    fn terminal_stat_row(&self, ui: &mut egui::Ui, name: &str, last_updated: Option<Instant>) {
        let status_str = if last_updated.is_some() { "OK" } else { "PENDING" };
        let status_color = if last_updated.is_some() { Color32::from_rgb(0xff, 0x00, 0x90) } else { Color32::from_rgb(0x80, 0x85, 0x90) };
        ui.label(
            RichText::new(format!("{:<22}: [{}]", name, status_str))
                .color(status_color)
                .monospace()
                .size(10.0)
        );
    }

    fn draw_waveform(&self, ui: &mut egui::Ui, color: Color32, height: f32, speed: f32, amp_mult: f32) {
        let (rect, _) = ui.allocate_exact_size(egui::vec2(ui.available_width(), height), egui::Sense::hover());
        let painter = ui.painter();
        
        // Draw baseline
        painter.line_segment(
            [egui::pos2(rect.min.x, rect.center().y), egui::pos2(rect.max.x, rect.center().y)],
            egui::Stroke::new(1.0_f32, Color32::from_rgb(0x1a, 0x05, 0x12))
        );
        
        let time = ui.input(|i| i.time) as f32;
        let points = 60;
        let step = rect.width() / (points as f32);
        let center_y = rect.center().y;
        let amplitude = height * 0.35_f32 * amp_mult;
        
        let mut prev_point: Option<egui::Pos2> = None;
        
        for i in 0..=points {
            let x = rect.min.x + (i as f32) * step;
            let freq1 = 0.12_f32;
            let freq2 = 0.25_f32;
            let val = ((i as f32 * freq1 + time * speed).sin() * 0.6_f32 + (i as f32 * freq2 - time * speed * 1.4_f32).cos() * 0.4_f32) * amplitude;
            let y = center_y + val;
            let current_pos = egui::pos2(x, y);
            
            if let Some(prev) = prev_point {
                painter.line_segment([prev, current_pos], egui::Stroke::new(1.5_f32, color));
            }
            prev_point = Some(current_pos);
        }
        
        if amp_mult > 0.0_f32 {
            ui.ctx().request_repaint();
        }
    }

    fn zenless_optimizer_request_export(&mut self, target: OptimizerExportTarget, include_characters: bool) {
        let (tx, rx) = oneshot::channel();
        let mut settings = self.saved_state.export_settings.clone();
        settings.include_characters = include_characters;
        settings.include_artifacts = true; // Always include Discs
        let _ = self.ui_message_tx.send(Message::ExportZenlessOptimizer(
            settings,
            tx,
        ));
        self.zzz_export_target = target;
        self.zzz_export_rx = Some(rx);
    }

    fn zenless_optimizer_handle_export(&mut self, ui: &mut egui::Ui) -> Result<()> {
        let Some(rx) = self.zzz_export_rx.take() else {
            return Ok(());
        };

        let json = rx.blocking_recv()??;

        match self.zzz_export_target {
            OptimizerExportTarget::None => {
                tracing::warn!("Unexpected json export");
            }
            OptimizerExportTarget::Clipboard => {
                ui.ctx().copy_text(json);
                self.toasts.info("Inter-Knot records copied to clipboard. Go optimize your Drive Discs, human.");
            }
            OptimizerExportTarget::File => {
                let path = self
                    .zzz_save_path
                    .take()
                    .ok_or_else(|| anyhow!("No ZZZ save file path set"))?;

                let file = File::create(&path).with_context(|| format!("Unable to open file {path:?}"))?;
                let mut writer = BufWriter::new(file);
                writer.write_all(json.as_bytes())?;

                self.toasts.info("Inter-Knot records archived to file. Injection file ready.");
            }
        }

        self.zzz_export_target = OptimizerExportTarget::None;
        Ok(())
    }

    fn zzz_settings_modal(&mut self, ui: &mut egui::Ui) {
        ui.set_width(300.0);
        ui.heading("INTER-KNOT DECRYPTION MATRIX");
        ui.separator();

        ui.checkbox(
            &mut self.saved_state.export_settings.include_characters,
            "Agent Combat Data",
        );
        ui.horizontal(|ui| {
            ui.add_space(20.);
            egui::Grid::new("agent_options")
                .striped(true)
                .show(ui, |ui| {
                    ui.label("Min Combat Level".to_string());
                    ui.add(
                        DragValue::new(&mut self.saved_state.export_settings.min_character_level)
                            .range(1..=60),
                    );
                    ui.end_row();
                    ui.label("Min Promotion Phase".to_string());
                    ui.add(
                        DragValue::new(
                            &mut self.saved_state.export_settings.min_character_ascension,
                        )
                        .range(0..=6),
                    );
                    ui.end_row();
                    ui.label("Min Mindscape Cinema".to_string());
                    ui.add(
                        DragValue::new(
                            &mut self.saved_state.export_settings.min_character_constellation,
                        )
                        .range(0..=6),
                    );
                    ui.end_row();
                });
        });
        ui.checkbox(
            &mut self.saved_state.export_settings.include_artifacts,
            "Drive Disc Partitions",
        );
        ui.horizontal(|ui| {
            ui.add_space(20.);
            egui::Grid::new("disc_options")
                .striped(true)
                .show(ui, |ui| {
                    ui.label("Min Level".to_string());
                    ui.add(
                        DragValue::new(&mut self.saved_state.export_settings.min_artifact_level)
                            .range(0..=15),
                    );
                    ui.end_row();
                    ui.label("Min Rarity".to_string());
                    ui.add(
                        DragValue::new(&mut self.saved_state.export_settings.min_artifact_rarity)
                            .range(2..=4),
                    );
                    ui.end_row();
                });
        });
        ui.checkbox(
            &mut self.saved_state.export_settings.include_weapons,
            "W-Engine Cores",
        );
        ui.horizontal(|ui| {
            ui.add_space(20.);
            egui::Grid::new("wengine_options")
                .striped(true)
                .show(ui, |ui| {
                    ui.label("Min Core Level".to_string());
                    ui.add(
                        DragValue::new(&mut self.saved_state.export_settings.min_weapon_level)
                            .range(1..=60),
                    );
                    ui.end_row();

                    ui.label("Min Refinement".to_string());
                    ui.add(
                        DragValue::new(&mut self.saved_state.export_settings.min_weapon_refinement)
                            .range(1..=5),
                    );
                    ui.end_row();

                    ui.label("Min Promotion Phase".to_string());
                    ui.add(
                        DragValue::new(&mut self.saved_state.export_settings.min_weapon_ascension)
                            .range(0..=6),
                    );
                    ui.end_row();

                    ui.label("Min Rarity".to_string());
                    ui.add(
                        DragValue::new(&mut self.saved_state.export_settings.min_weapon_rarity)
                            .range(2..=4),
                    );
                    ui.end_row();
                });
        });
        ui.separator();
        egui::Sides::new().show(
            ui,
            |_ui| {},
            |ui| {
                if ui.button("Ok").clicked() {
                    ui.close()
                }
            },
        );
    }



    fn power_tools_modal(&mut self, ui: &mut egui::Ui) {
        ui.set_width(300.0);
        ui.heading("Power Tools");
        ui.separator();
        if ui
            .checkbox(&mut self.saved_state.log_raw_packets, "Log raw packets")
            .changed()
        {
            let _ = self.log_packets_tx.send(self.saved_state.log_raw_packets);
        };
        let prev_level = self.saved_state.tracing_level;
        egui::ComboBox::from_label("Logging Level")
            .selected_text(format!("{}", self.saved_state.tracing_level))
            .show_ui(ui, |ui| {
                ui.selectable_value(
                    &mut self.saved_state.tracing_level,
                    TracingLevel::Default,
                    "Default",
                );
                ui.selectable_value(
                    &mut self.saved_state.tracing_level,
                    TracingLevel::VerboseInfo,
                    "Verbose Info",
                );
                ui.selectable_value(
                    &mut self.saved_state.tracing_level,
                    TracingLevel::VerboseDebug,
                    "Verbose Debug",
                );
                ui.selectable_value(
                    &mut self.saved_state.tracing_level,
                    TracingLevel::VerboseTrace,
                    "Verbose Trace",
                );
            });
        if prev_level != self.saved_state.tracing_level {
            self.tracing_reload_handle
                .set_filter(self.saved_state.tracing_level.get_filter());
        }
        ui.end_row();
        ui.separator();
        egui::Sides::new().show(
            ui,
            |_ui| {},
            |ui| {
                if ui.button("Ok").clicked() {
                    ui.close()
                }
            },
        );
    }

    fn bug_report_modal(&mut self, ui: &mut egui::Ui) {
        ui.set_width(300.0);
        ui.heading("Bug Report");
        ui.separator();
        ui.label("When filing a bug, please include the latest log file:");
        if ui.button("Open log directory").clicked() {
            thread::spawn(|| {
                let _ = open_log_dir();
            });
        }
        ui.separator();
        egui::Sides::new().show(
            ui,
            |_ui| {},
            |ui| {
                if ui.button("New GitHub Issue").clicked() {
                    ui.ctx().open_url(OpenUrl::new_tab(
                        "https://github.com/konkers/irminsul/issues/new",
                    ));
                    ui.close()
                }
                if ui.button("Cancel").clicked() {
                    ui.close()
                }
            },
        );
    }

    fn capture_settings_modal(&mut self, ui: &mut egui::Ui) {
        ui.set_width(300.0);
        ui.heading("INTRUSION METRICS");
        ui.separator();
        ui.checkbox(
            &mut self.saved_state.auto_start_capture,
            "Auto-infiltrate network on launch",
        );
        ui.checkbox(
            &mut self.saved_state.capture_all_udp,
            "Rogue Mode: Siphon all UDP packets",
        );
        ui.separator();
        egui::Sides::new().show(
            ui,
            |_ui| {},
            |ui| {
                if ui.button("Ok").clicked() {
                    ui.close()
                }
            },
        );
    }



    fn section_header(ui: &mut egui::Ui, name: &str) {
        ui.label(RichText::new(name).size(18.));
    }
}
