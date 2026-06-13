use std::{fs, thread};

use egui::{
    Button, Color32, Id, Key, KeyboardShortcut, Modal, Modifiers, OpenUrl,
    PointerButton, RichText, Sense, ViewportCommand,
};
use egui_file_dialog::FileDialog;
use egui_notify::Toasts;
use serde::{Deserialize, Serialize};

use crate::{
    ReloadHandle, ScanConfig, ScanHandle, ScanMode, ScanPhase, ScanState,
    TracingLevel, open_log_dir,
};

#[derive(Clone, Copy, PartialEq)]
enum FileDialogPurpose {
    OutputPath,
    ExportFile,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SavedAppState {
    #[serde(default)]
    tracing_level: TracingLevel,
    #[serde(default)]
    pub scan_config: ScanConfig,
}

impl Default for SavedAppState {
    fn default() -> Self {
        Self { tracing_level: Default::default(), scan_config: Default::default() }
    }
}

pub struct YoukaiApp {
    tracing_reload_handle: ReloadHandle,
    toasts: Toasts,
    power_tools_open: bool,
    bug_report_open: bool,
    pub scan_state: ScanState,
    saved_state: SavedAppState,
    scan_handle: Option<ScanHandle>,
    file_dialog: FileDialog,
    file_dialog_purpose: FileDialogPurpose,
    occlusion_minimized: bool,
}

impl YoukaiApp {
    pub fn new(cc: &eframe::CreationContext<'_>, mut tracing_reload_handle: ReloadHandle) -> Self {
        egui_extras::install_image_loaders(&cc.egui_ctx);
        egui_material_icons::initialize(&cc.egui_ctx);

        cc.egui_ctx.style_mut(|style| {
            style.visuals.window_corner_radius = egui::CornerRadius::ZERO;
            style.visuals.widgets.noninteractive.corner_radius = egui::CornerRadius::ZERO;
            style.visuals.widgets.inactive.corner_radius = egui::CornerRadius::ZERO;
            style.visuals.widgets.hovered.corner_radius = egui::CornerRadius::ZERO;
            style.visuals.widgets.active.corner_radius = egui::CornerRadius::ZERO;
            style.visuals.widgets.open.corner_radius = egui::CornerRadius::ZERO;

            style.visuals.dark_mode = true;

            let bg_color = Color32::from_rgb(0x00, 0x00, 0x00);
            let widget_inactive_bg = Color32::from_rgb(0x0c, 0x06, 0x12);
            let widget_hovered_bg = Color32::from_rgb(0xff, 0x00, 0x90);
            let widget_active_bg = Color32::from_rgb(0xc2, 0x00, 0x6d);

            let text_color_light = Color32::from_rgb(0xfd, 0xf5, 0xfa);
            let text_color_dark = Color32::from_rgb(0x00, 0x00, 0x00);

            style.visuals.override_text_color = Some(text_color_light);
            style.visuals.window_fill = bg_color;
            style.visuals.panel_fill = bg_color;

            style.visuals.widgets.inactive.bg_fill = widget_inactive_bg;
            style.visuals.widgets.inactive.bg_stroke =
                egui::Stroke::new(1.0, Color32::from_rgb(0xa8, 0x2b, 0x72));
            style.visuals.widgets.inactive.fg_stroke =
                egui::Stroke::new(1.5, Color32::from_rgb(0xa8, 0x2b, 0x72));
            style.visuals.widgets.inactive.weak_bg_fill = widget_inactive_bg;

            style.visuals.widgets.hovered.bg_fill = widget_hovered_bg;
            style.visuals.widgets.hovered.fg_stroke =
                egui::Stroke::new(2.0, text_color_dark);
            style.visuals.widgets.hovered.weak_bg_fill = widget_hovered_bg;

            style.visuals.widgets.active.bg_fill = widget_active_bg;
            style.visuals.widgets.active.fg_stroke =
                egui::Stroke::new(2.0, text_color_dark);
            style.visuals.widgets.active.weak_bg_fill = widget_active_bg;

            style.visuals.widgets.noninteractive.bg_fill = bg_color;
            style.visuals.widgets.noninteractive.fg_stroke =
                egui::Stroke::new(1.0, Color32::from_rgb(0x4d, 0x15, 0x38));

            for font_id in style.text_styles.values_mut() {
                font_id.family = egui::FontFamily::Monospace;
            }
        });

        let saved_state: SavedAppState = if let Some(storage) = cc.storage {
            eframe::get_value(storage, eframe::APP_KEY).unwrap_or_default()
        } else {
            Default::default()
        };

        tracing_reload_handle.set_filter(saved_state.tracing_level.get_filter());

        let toasts = Toasts::default().with_anchor(egui_notify::Anchor::BottomLeft);

        Self {
            tracing_reload_handle,
            toasts,
            power_tools_open: false,
            bug_report_open: false,
            scan_state: ScanState::Idle,
            saved_state,
            scan_handle: None,
            file_dialog: FileDialog::new(),
            file_dialog_purpose: FileDialogPurpose::OutputPath,
            occlusion_minimized: false,
        }
    }
}

impl eframe::App for YoukaiApp {
    fn save(&mut self, storage: &mut dyn eframe::Storage) {
        eframe::set_value(storage, eframe::APP_KEY, &self.saved_state);
    }

    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        // Poll scan handle every frame
        if let Some(h) = &self.scan_handle {
            let new_state = h.state();
            let is_terminal =
                matches!(new_state, ScanState::Done { .. } | ScanState::Failed { .. });
            self.scan_state = new_state;
            if is_terminal {
                self.scan_handle = None;
                // Load-bearing: reader_thread calls request_repaint() on the terminal event,
                // which wakes the minimized window so update() can un-minimize. Do not remove.
                if self.occlusion_minimized {
                    ctx.send_viewport_cmd(ViewportCommand::Minimized(false));
                    ctx.send_viewport_cmd(ViewportCommand::RequestUserAttention(
                        egui::UserAttentionType::Informational,
                    ));
                    self.occlusion_minimized = false;
                }
            }
        }

        // Process file dialog results
        self.file_dialog.update(ctx);
        if let Some(path) = self.file_dialog.take_picked() {
            match self.file_dialog_purpose {
                FileDialogPurpose::OutputPath => {
                    self.saved_state.scan_config.output = path;
                }
                FileDialogPurpose::ExportFile => {
                    if let ScanState::Done { ref output, .. } = self.scan_state.clone() {
                        match fs::copy(output, &path) {
                            Ok(_) => {
                                self.toasts.info(format!(
                                    "Exported to {}",
                                    path.file_name()
                                        .and_then(|n| n.to_str())
                                        .unwrap_or("file")
                                ));
                            }
                            Err(e) => {
                                self.toasts.error(format!("Export failed: {e}"));
                            }
                        }
                    }
                }
            }
        }

        let mut clicked_exit = false;
        ctx.style_mut(|style| {
            style.interaction.selectable_labels = false;
            style.interaction.tooltip_delay = 0.25;
        });

        self.toasts.show(ctx);

        egui::CentralPanel::default().show(ctx, |ui| {
            let rect = ui.max_rect();
            ui.painter().rect_filled(rect, egui::Rounding::ZERO, Color32::from_rgb(0, 0, 0));

            ui.vertical(|ui| {
                clicked_exit = self.title_bar(ui);
                ui.add_space(10.);

                let power_tools_shortcut = KeyboardShortcut {
                    modifiers: Modifiers { command: true, shift: true, ..Default::default() },
                    logical_key: Key::P,
                };
                ui.ctx().input_mut(|i| {
                    if i.consume_shortcut(&power_tools_shortcut) {
                        self.power_tools_open = true;
                    }
                });

                if self.power_tools_open {
                    let modal = Modal::new(Id::new("Power Tools"))
                        .show(ui.ctx(), |ui| self.power_tools_modal(ui));
                    if modal.should_close() {
                        self.power_tools_open = false;
                    }
                }

                if self.bug_report_open {
                    let modal = Modal::new(Id::new("Bug Report"))
                        .show(ui.ctx(), |ui| self.bug_report_modal(ui));
                    if modal.should_close() {
                        self.bug_report_open = false;
                    }
                }

                // Grid_OS double-line window frame
                let window_rect = rect.shrink2(egui::vec2(20.0, 40.0));
                let frame_stroke_outer =
                    egui::Stroke::new(1.5, Color32::from_rgb(0xff, 0x00, 0x90));
                let frame_stroke_inner =
                    egui::Stroke::new(0.8, Color32::from_rgb(0xff, 0x00, 0x90));
                ui.painter().rect_stroke(
                    window_rect,
                    egui::Rounding::ZERO,
                    frame_stroke_outer,
                    egui::StrokeKind::Inside,
                );
                ui.painter().rect_stroke(
                    window_rect.shrink(3.0),
                    egui::Rounding::ZERO,
                    frame_stroke_inner,
                    egui::StrokeKind::Inside,
                );

                ui.allocate_ui_at_rect(window_rect.shrink(8.0), |ui| {
                    ui.shrink_clip_rect(window_rect.shrink(8.0));
                    ui.vertical(|ui| {
                        ui.horizontal(|ui| {
                            ui.label(
                                RichText::new("// SYSTEM STATUS // YOUKAI_GRID_OS v9.4")
                                    .color(Color32::from_rgb(0xff, 0x00, 0x90))
                                    .strong()
                                    .size(11.0),
                            );
                        });
                        ui.separator();
                        ui.add_space(8.0);

                        self.main_ui(ui, ctx);
                    });
                });
            });

            ui.with_layout(egui::Layout::bottom_up(egui::Align::RIGHT), |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        RichText::new(format!("v{}", env!("CARGO_PKG_VERSION")))
                            .color(Color32::from_rgb(0xa8, 0x2b, 0x72))
                            .size(8.0),
                    );
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
        let clock_str = chrono::Local::now()
            .format("%Y.%m.%d // %H:%M:%S %Z")
            .to_string();
        let mut clicked_exit = false;

        egui::Sides::new().show(
            ui,
            |ui| {
                ui.horizontal(|ui| {
                    ui.add_space(8.0);
                    let logo = egui::Image::new(egui::include_image!("../../assets/icon-256.png"))
                        .max_width(20.0)
                        .max_height(20.0);
                    ui.add(logo);
                });
            },
            |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        RichText::new(clock_str)
                            .monospace()
                            .color(Color32::from_rgb(0xff, 0x00, 0x90))
                            .size(11.0),
                    );
                    ui.add_space(10.0);
                    let button = ui.add(
                        Button::new(
                            RichText::new(" EXIT ")
                                .strong()
                                .monospace()
                                .color(Color32::from_rgb(0, 0, 0)),
                        )
                        .fill(Color32::from_rgb(0xff, 0x00, 0x55))
                        .stroke(egui::Stroke::new(1.0, Color32::from_rgb(0xff, 0x00, 0x55))),
                    );
                    if button.clicked() {
                        clicked_exit = true;
                        ui.ctx().send_viewport_cmd(ViewportCommand::Close);
                    }
                });
            },
        );

        let app_rect = ui.max_rect();
        let title_bar_height = 32.0;
        let title_bar_rect = {
            let mut rect = app_rect;
            rect.max.y = rect.min.y + title_bar_height;
            rect.max.x = rect.min.x + 480.0;
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

    fn main_ui(&mut self, ui: &mut egui::Ui, ctx: &egui::Context) {
        let is_scanning = self.scan_handle.is_some();

        if !crate::ui::admin::is_admin() {
            egui::Frame::none()
                .fill(Color32::from_rgb(0x1a, 0x0a, 0x00))
                .stroke(egui::Stroke::new(1.2, Color32::from_rgb(0xff, 0x88, 0x00)))
                .inner_margin(8.0)
                .show(ui, |ui| {
                    ui.label(
                        RichText::new("⚠ NOT RUNNING AS ADMINISTRATOR")
                            .color(Color32::from_rgb(0xff, 0x88, 0x00))
                            .strong()
                            .size(11.0),
                    );
                    ui.add_space(2.0);
                    ui.label(
                        RichText::new(
                            "ZZZ runs elevated under anti-cheat. Screen capture and \
                             synthetic input require matching elevation. \
                             Right-click youkai.exe → Run as administrator.",
                        )
                        .color(Color32::from_rgb(0xcc, 0x88, 0x44))
                        .size(10.5),
                    );
                });
            ui.add_space(6.0);
        }

        ui.with_layout(egui::Layout::left_to_right(egui::Align::TOP), |ui| {
            // ── LEFT COLUMN ──────────────────────────────────────────
            ui.vertical(|ui| {
                ui.set_width(360.0);

                ui.label(
                    RichText::new("// ACTIVE SCAN PIPELINE")
                        .color(Color32::from_rgb(0xff, 0x00, 0x90))
                        .strong()
                        .size(11.0),
                );
                ui.add_space(4.0);

                let terminal_height = ui.available_height() - 6.0;
                egui::Frame::canvas(ui.style())
                    .fill(Color32::from_rgb(0x07, 0x03, 0x0b))
                    .stroke(egui::Stroke::new(1.0, Color32::from_rgb(0x3d, 0x0f, 0x28)))
                    .inner_margin(12.0)
                    .show(ui, |ui| {
                        ui.set_height(terminal_height);
                        ui.set_clip_rect(ui.clip_rect().intersect(ui.max_rect()));
                        ui.vertical(|ui| {
                            ui.label(
                                RichText::new("YOUKAI // INT_CMD_LINE")
                                    .color(Color32::from_rgb(0xff, 0x00, 0x90))
                                    .strong()
                                    .size(10.0),
                            );
                            ui.separator();
                            ui.add_space(4.0);

                            let (status_str, status_color, dialogue) = match &self.scan_state {
                                ScanState::Idle => (
                                    "IDLE",
                                    Color32::from_rgb(0x80, 0x85, 0x90),
                                    "Ensure ZZZ is running in windowed mode on the\nInter-Knot main hub, fully unobscured,\nwith Night Light disabled.",
                                ),
                                ScanState::Running { phase, .. } => {
                                    let phase_str = match phase {
                                        Some(ScanPhase::Engines) => "SCANNING: W-ENGINES",
                                        Some(ScanPhase::Discs) => "SCANNING: DRIVE DISCS",
                                        Some(ScanPhase::Agents) => "SCANNING: AGENTS",
                                        None => "SCANNING",
                                    };
                                    (
                                        phase_str,
                                        Color32::from_rgb(0xff, 0x00, 0x90),
                                        "Extraction in progress.\nKeep the game window visible and unobscured.",
                                    )
                                }
                                ScanState::Done { .. } => (
                                    "COMPLETE",
                                    Color32::from_rgb(0xff, 0x00, 0x90),
                                    "Extraction complete.\nOutput ready — see right column.",
                                ),
                                ScanState::Failed { message, .. } => (
                                    "FAILED",
                                    Color32::from_rgb(0xff, 0x00, 0x55),
                                    // truncate long error to first line for dialogue
                                    {
                                        let _ = message; // accessed via pattern below
                                        "Extraction failed.\nSee right column for details."
                                    },
                                ),
                            };

                            ui.label(
                                RichText::new(format!("SCAN STATUS    : [{}]", status_str))
                                    .color(status_color)
                                    .monospace()
                                    .size(10.0),
                            );
                            ui.label(
                                RichText::new(
                                    "TARGET         : [ INTER-KNOT DATABASE ]",
                                )
                                .color(Color32::from_rgb(0xff, 0xf0, 0xf8))
                                .monospace()
                                .size(10.0),
                            );

                            ui.add_space(12.0);

                            ui.label(
                                RichText::new(dialogue)
                                    .color(Color32::from_rgb(0xa8, 0x2b, 0x72))
                                    .size(10.0),
                            );

                            ui.with_layout(egui::Layout::bottom_up(egui::Align::Min), |ui| {
                                ui.vertical(|ui| {
                                    // Stat rows
                                    let (eng_val, eng_col) = self.phase_display("engines");
                                    let (disc_val, disc_col) = self.phase_display("discs");
                                    let (agent_val, agent_col) = self.phase_display("agents");
                                    self.scan_stat_row(ui, "W-Engine Cores  ", &eng_val, eng_col);
                                    self.scan_stat_row(ui, "Drive Discs     ", &disc_val, disc_col);
                                    self.scan_stat_row(
                                        ui,
                                        "Agent Files     ",
                                        &agent_val,
                                        agent_col,
                                    );

                                    ui.add_space(8.0);

                                    // Progress bar
                                    let progress_bar = match &self.scan_state {
                                        ScanState::Running { scanned, total, .. } => {
                                            let filled = match total {
                                                Some(t) if *t > 0 => {
                                                    ((*scanned as f32 / *t as f32) * 10.0)
                                                        .round()
                                                        as usize
                                                }
                                                _ => {
                                                    (ui.input(|i| i.time * 4.0) as usize) % 11
                                                }
                                            };
                                            let bar: String = (0..10)
                                                .map(|j| if j < filled { "■" } else { " " })
                                                .collect();
                                            format!("[{}]", bar)
                                        }
                                        ScanState::Done { .. } => "[■■■■■■■■■■]".to_string(),
                                        _ => "[          ]".to_string(),
                                    };

                                    ui.label(
                                        RichText::new(progress_bar)
                                            .color(Color32::from_rgb(0xff, 0x00, 0x90))
                                            .monospace()
                                            .strong(),
                                    );

                                    ui.add_space(8.0);

                                    // Waveform — animates only while Running
                                    let (amp, speed) =
                                        if matches!(self.scan_state, ScanState::Running { .. }) {
                                            (1.0, 8.0)
                                        } else {
                                            (0.0, 0.0)
                                        };
                                    self.draw_waveform(
                                        ui,
                                        Color32::from_rgb(0xff, 0x00, 0x90),
                                        24.0,
                                        speed,
                                        amp,
                                    );

                                    ui.add_space(8.0);

                                    // EXECUTE / KILL button
                                    ui.horizontal(|ui| {
                                        if is_scanning {
                                            let kill_btn = ui.add(
                                                Button::new(
                                                    RichText::new(" KILL EXTRACTION SCRIPT ")
                                                        .monospace()
                                                        .color(Color32::from_rgb(0, 0, 0))
                                                        .size(10.0),
                                                )
                                                .fill(Color32::from_rgb(0xff, 0x00, 0x55))
                                                .stroke(egui::Stroke::new(
                                                    1.0,
                                                    Color32::from_rgb(0xff, 0x00, 0x55),
                                                )),
                                            );
                                            if kill_btn.clicked() {
                                                if let Some(h) = &self.scan_handle {
                                                    h.kill();
                                                }
                                            }
                                        } else {
                                            let exec_btn = ui.add(
                                                Button::new(
                                                    RichText::new(
                                                        " EXECUTE EXTRACTION SCRIPT ",
                                                    )
                                                    .monospace()
                                                    .size(10.0),
                                                ),
                                            );
                                            if exec_btn.clicked() {
                                                self.scan_state = ScanState::Idle;
                                                self.scan_handle = Some(ScanHandle::start(
                                                    self.saved_state.scan_config.clone(),
                                                    Some(ctx.clone()),
                                                ));
                                                ctx.send_viewport_cmd(
                                                    ViewportCommand::Minimized(true),
                                                );
                                                self.occlusion_minimized = true;
                                            }
                                        }
                                    });
                                });
                            });
                        });
                    });
            });

            ui.add_space(16.0);

            // ── RIGHT COLUMN ─────────────────────────────────────────
            ui.vertical(|ui| {
                let right_width = ui.available_width() - 6.0;
                ui.set_width(right_width);

                // Map image
                let map_height = 180.0;
                egui::Frame::canvas(ui.style())
                    .fill(Color32::from_rgb(0, 0, 0))
                    .stroke(egui::Stroke::new(1.0, Color32::from_rgb(0x4d, 0x15, 0x38)))
                    .inner_margin(0.0)
                    .show(ui, |ui| {
                        let map_image =
                            egui::Image::new(egui::include_image!("../../assets/map.webp"))
                                .max_height(map_height)
                                .max_width(right_width);
                        let response = ui.add(map_image);
                        let rect = response.rect;
                        let painter = ui.painter();
                        let center =
                            egui::pos2(rect.min.x + rect.width() * 0.64, rect.center().y);
                        let color = Color32::from_rgb(0xff, 0x00, 0x90);
                        painter.circle_stroke(center, 13.0, egui::Stroke::new(1.6, color));
                        painter.circle_filled(center, 2.2, color);
                        painter.line_segment(
                            [center - egui::vec2(0.0, 24.0), center - egui::vec2(0.0, 13.0)],
                            egui::Stroke::new(1.6, color),
                        );
                        painter.line_segment(
                            [center + egui::vec2(0.0, 13.0), center + egui::vec2(0.0, 24.0)],
                            egui::Stroke::new(1.6, color),
                        );
                        painter.line_segment(
                            [center - egui::vec2(24.0, 0.0), center - egui::vec2(13.0, 0.0)],
                            egui::Stroke::new(1.6, color),
                        );
                        painter.line_segment(
                            [center + egui::vec2(13.0, 0.0), center + egui::vec2(24.0, 0.0)],
                            egui::Stroke::new(1.6, color),
                        );
                        painter.text(
                            center + egui::vec2(22.0, -16.0),
                            egui::Align2::LEFT_TOP,
                            "TARGET\nACQUIRED",
                            egui::FontId::new(16.0, egui::FontFamily::Monospace),
                            color,
                        );
                    });

                ui.add_space(8.0);

                // Parameters / results panel
                let params_height = ui.available_height() - 6.0;
                egui::Frame::canvas(ui.style())
                    .fill(Color32::from_rgb(0x07, 0x03, 0x0b))
                    .stroke(egui::Stroke::new(1.0, Color32::from_rgb(0x3d, 0x0f, 0x28)))
                    .inner_margin(8.0)
                    .show(ui, |ui| {
                        ui.set_height(params_height);
                        ui.set_clip_rect(ui.clip_rect().intersect(ui.max_rect()));
                        ui.vertical(|ui| {
                            self.params_panel(ui, is_scanning);
                        });
                    });
            });
        });
    }

    fn params_panel(&mut self, ui: &mut egui::Ui, is_scanning: bool) {
        // Snapshot the state variant to decide which panel to show
        let is_done = matches!(self.scan_state, ScanState::Done { .. });
        let is_failed = matches!(self.scan_state, ScanState::Failed { .. });

        if is_done {
            self.params_done(ui);
        } else if is_failed {
            self.params_failed(ui);
        } else {
            self.params_config(ui, is_scanning);
        }
    }

    fn params_config(&mut self, ui: &mut egui::Ui, is_scanning: bool) {
        ui.spacing_mut().item_spacing.y = 2.0;
        ui.label(
            RichText::new("// SCAN PARAMETERS")
                .color(Color32::from_rgb(0xff, 0x00, 0x90))
                .strong()
                .size(10.0),
        );
        ui.separator();

        // Mode selection
        ui.label(
            RichText::new("EXTRACTION MODE")
                .color(Color32::from_rgb(0xa8, 0x2b, 0x72))
                .monospace()
                .size(9.0),
        );
        ui.add_enabled_ui(!is_scanning, |ui| {
            ui.radio_value(
                &mut self.saved_state.scan_config.mode,
                ScanMode::Full,
                RichText::new("FULL SIPHON  (agents + discs + engines)")
                    .monospace()
                    .size(9.5),
            );
            ui.radio_value(
                &mut self.saved_state.scan_config.mode,
                ScanMode::DiscsOnly,
                RichText::new("DISC PARTITIONS ONLY").monospace().size(9.5),
            );
        });

        ui.add_space(4.0);

        // Debug overlays
        ui.add_enabled_ui(!is_scanning, |ui| {
            ui.checkbox(
                &mut self.saved_state.scan_config.debug_overlays,
                RichText::new("debug overlays").monospace().size(9.5),
            );
        });

    }

    fn params_done(&mut self, ui: &mut egui::Ui) {
        // Clone out what we need before borrowing ui
        let (output, run_dir, review_path, issues) =
            if let ScanState::Done { output, run_dir, review_path, summary } = &self.scan_state {
                (output.clone(), run_dir.clone(), review_path.clone(), summary.issues)
            } else {
                return;
            };

        ui.label(
            RichText::new("// EXTRACTION COMPLETE")
                .color(Color32::from_rgb(0xff, 0x00, 0x90))
                .strong()
                .size(10.0),
        );
        ui.separator();
        ui.add_space(6.0);

        // Copy to clipboard
        if ui
            .add(
                Button::new(
                    RichText::new(" COPY TO CLIPBOARD ").monospace().size(9.5),
                )
                .min_size(egui::vec2(ui.available_width() - 4.0, 0.0)),
            )
            .clicked()
        {
            match fs::read_to_string(&output) {
                Ok(text) => {
                    ui.ctx().copy_text(text);
                    self.toasts.info("Copied to clipboard.");
                }
                Err(e) => {
                    self.toasts
                        .error(format!("Read failed: {e}"));
                }
            }
        }

        ui.add_space(4.0);

        // Export file
        if ui
            .add(
                Button::new(RichText::new(" EXPORT FILE... ").monospace().size(9.5))
                    .min_size(egui::vec2(ui.available_width() - 4.0, 0.0)),
            )
            .clicked()
        {
            let default_name = output
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("youkai_export.json")
                .to_string();
            self.file_dialog.config_mut().default_file_name = default_name;
            self.file_dialog_purpose = FileDialogPurpose::ExportFile;
            self.file_dialog.save_file();
        }

        ui.add_space(4.0);

        // Open run directory
        if ui
            .add(
                Button::new(RichText::new(" OPEN RUN DIR ").monospace().size(9.5))
                    .min_size(egui::vec2(ui.available_width() - 4.0, 0.0)),
            )
            .clicked()
        {
            let rd = run_dir.clone();
            thread::spawn(move || {
                let _ = open::that(rd);
            });
        }

        // Review report — only shown when issues > 0
        if issues > 0 {
            if let Some(rp) = &review_path {
                ui.add_space(4.0);
                let rp = rp.clone();
                if ui
                    .add(
                        Button::new(
                            RichText::new(format!(" REVIEW REPORT ({} issues) ", issues))
                                .monospace()
                                .size(9.5),
                        )
                        .fill(Color32::from_rgb(0x28, 0x10, 0x00))
                        .stroke(egui::Stroke::new(
                            1.0,
                            Color32::from_rgb(0xff, 0x60, 0x00),
                        ))
                        .min_size(egui::vec2(ui.available_width() - 4.0, 0.0)),
                    )
                    .clicked()
                {
                    thread::spawn(move || {
                        let _ = open::that(rp);
                    });
                }
            }
        }

        ui.add_space(12.0);
        ui.separator();
        ui.add_space(6.0);

        if ui
            .add(
                Button::new(RichText::new(" NEW SCAN ").monospace().size(9.5))
                    .min_size(egui::vec2(ui.available_width() - 4.0, 0.0)),
            )
            .clicked()
        {
            self.scan_state = ScanState::Idle;
        }
    }

    fn params_failed(&mut self, ui: &mut egui::Ui) {
        let (message, run_dir) =
            if let ScanState::Failed { message, run_dir } = &self.scan_state {
                (message.clone(), run_dir.clone())
            } else {
                return;
            };

        ui.label(
            RichText::new("// EXTRACTION FAILED")
                .color(Color32::from_rgb(0xff, 0x00, 0x55))
                .strong()
                .size(10.0),
        );
        ui.separator();
        ui.add_space(4.0);

        egui::ScrollArea::vertical().max_height(140.0).show(ui, |ui| {
            ui.label(
                RichText::new(&message)
                    .monospace()
                    .size(8.5)
                    .color(Color32::from_rgb(0xff, 0x60, 0x60)),
            );
        });

        ui.add_space(6.0);

        if let Some(rd) = run_dir {
            if ui
                .add(
                    Button::new(RichText::new(" OPEN RUN DIR ").monospace().size(9.5))
                        .min_size(egui::vec2(ui.available_width() - 4.0, 0.0)),
                )
                .clicked()
            {
                thread::spawn(move || {
                    let _ = open::that(rd);
                });
            }
            ui.add_space(4.0);
        }

        ui.separator();
        ui.add_space(6.0);

        if ui
            .add(
                Button::new(RichText::new(" NEW SCAN ").monospace().size(9.5))
                    .min_size(egui::vec2(ui.available_width() - 4.0, 0.0)),
            )
            .clicked()
        {
            self.scan_state = ScanState::Idle;
        }
    }

    fn phase_display(&self, phase: &str) -> (String, Color32) {
        let dim = Color32::from_rgb(0x80, 0x85, 0x90);
        let bright = Color32::from_rgb(0xff, 0x00, 0x90);
        let red = Color32::from_rgb(0xff, 0x00, 0x55);

        match &self.scan_state {
            ScanState::Idle => ("--".to_string(), dim),
            ScanState::Running { phase: cur_phase, scanned, total, counts } => {
                let done = match phase {
                    "engines" => counts.engines.as_ref().map(|r| r.count),
                    "discs" => counts.discs.as_ref().map(|r| r.count),
                    "agents" => counts.agents.as_ref().map(|r| r.count),
                    _ => None,
                };
                if let Some(n) = done {
                    return (format!("{}", n), bright);
                }
                let active = matches!(
                    (phase, cur_phase),
                    ("engines", Some(ScanPhase::Engines))
                        | ("discs", Some(ScanPhase::Discs))
                        | ("agents", Some(ScanPhase::Agents))
                );
                if active {
                    match total {
                        Some(t) => (format!("{}/{}", scanned, t), bright),
                        None => (format!("{}...", scanned), bright),
                    }
                } else {
                    ("--".to_string(), dim)
                }
            }
            ScanState::Done { summary, .. } => {
                let n = match phase {
                    "engines" => summary.engines,
                    "discs" => summary.discs,
                    "agents" => summary.agents,
                    _ => 0,
                };
                (format!("{}", n), bright)
            }
            ScanState::Failed { .. } => ("--".to_string(), red),
        }
    }

    fn scan_stat_row(&self, ui: &mut egui::Ui, label: &str, value: &str, color: Color32) {
        ui.label(
            RichText::new(format!("{}: [{}]", label, value))
                .color(color)
                .monospace()
                .size(10.0),
        );
    }

    fn draw_waveform(
        &self,
        ui: &mut egui::Ui,
        color: Color32,
        height: f32,
        speed: f32,
        amp_mult: f32,
    ) {
        let (rect, _) = ui.allocate_exact_size(
            egui::vec2(ui.available_width(), height),
            egui::Sense::hover(),
        );
        let painter = ui.painter();

        painter.line_segment(
            [
                egui::pos2(rect.min.x, rect.center().y),
                egui::pos2(rect.max.x, rect.center().y),
            ],
            egui::Stroke::new(1.0, Color32::from_rgb(0x1a, 0x05, 0x12)),
        );

        let time = ui.input(|i| i.time) as f32;
        let points = 60;
        let step = rect.width() / (points as f32);
        let center_y = rect.center().y;
        let amplitude = height * 0.35 * amp_mult;

        let mut prev_point: Option<egui::Pos2> = None;
        for i in 0..=points {
            let x = rect.min.x + (i as f32) * step;
            let val = ((i as f32 * 0.12 + time * speed).sin() * 0.6
                + (i as f32 * 0.25 - time * speed * 1.4).cos() * 0.4)
                * amplitude;
            let current_pos = egui::pos2(x, center_y + val);
            if let Some(prev) = prev_point {
                painter.line_segment([prev, current_pos], egui::Stroke::new(1.5, color));
            }
            prev_point = Some(current_pos);
        }

        if amp_mult > 0.0 {
            ui.ctx().request_repaint();
        }
    }

    fn power_tools_modal(&mut self, ui: &mut egui::Ui) {
        ui.set_width(300.0);
        ui.heading("Power Tools");
        ui.separator();
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
        ui.separator();
        egui::Sides::new().show(
            ui,
            |_ui| {},
            |ui| {
                if ui.button("Ok").clicked() {
                    ui.close();
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
                        "https://github.com/AJTDaedalus/youkai/issues/new",
                    ));
                    ui.close();
                }
                if ui.button("Cancel").clicked() {
                    ui.close();
                }
            },
        );
    }
}
