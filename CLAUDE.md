# Project Settings & Guidelines

This document outlines the structure, development workflow, and safety guidelines for the **youkai** project.

## Project Structure

*   **Main Project Folder (Windows Host)**: `C:\Users\laharre\OneDrive\Documents\youkai`
    *   *Purpose*: Planning documents, brain files, design specifications, and other non-code documentation live here.
*   **WSL Root Folder (Ubuntu Linux)**: `\\wsl.localhost\Ubuntu\root\youkai`
    *   *Purpose*: **Primary place for actual code work.**
    *   `irminsul/`: Pristine reference clone of the Genshin Impact sniffer. Do not modify.
    *   `youkai/`: **Active development folder** for the Zenless Zone Zero packet-sniffing and data exporter tool.

## Workflow Instructions

1.  **Code Edits**: Make code changes directly inside the new WSL directory: `\\wsl.localhost\Ubuntu\root\youkai\youkai`.
2.  **Command Execution**: Run build, test, or run commands targetting the WSL environment or from within the WSL filespace where appropriate.
3.  **Documentation & Planning**: Save planning artifacts, implementation plans (`implementation_plan.md`), task tracking (`task.md`), and walkthroughs (`walkthrough.md`) in the main project folder on the Windows host or in the designated brain/artifacts directories.

## Anti-Ban & Safety Guidelines

To protect your Zenless Zone Zero account from anti-cheat detection (HoyoPlay Anti-Cheat / APEX / HoyoProtect) and prevent bans, the development of Youkai must adhere to these absolute rules:

1.  **Strict Passivity (Network Level)**:
    *   Only use standard passive packet sniffing tools (like the Windows built-in `pktmon` driver). 
    *   Passive network interception does not modify, intercept, or inject data into the game client. The game client remains completely unaware that its network packets are being observed at the OS driver level.
2.  **No Memory Access**:
    *   **NEVER** use memory reading (`ReadProcessMemory`), memory writing (`WriteProcessMemory`), or DLL injection on the `ZenlessZoneZero.exe` process. Memory manipulation is immediately detected by the game's ring-0 kernel anti-cheat driver and triggers an instant, permanent account ban.
3.  **No Executable or Asset Modification**:
    *   Never modify, patch, rename, or tamper with the game executable or data files (e.g., `ZenlessZoneZero.exe`, `GameAssembly.dll`, or local asset bundles).
4.  **No Client-Side Proxies**:
    *   Avoid setting up active local HTTPS proxies (like mitmproxy/Fiddler with custom root certificates) for routing main game traffic, as SSL certificate pinning checks in modern HoYoverse clients can easily flag custom certificate authority authorities.
5.  **Safe Testing Best Practices**:
    *   When first testing Youkai's packet parser or decryption logic on live game sessions, **always test using a secondary/alt account** rather than your primary main account to guarantee complete safety.
6.  **OS-Side Input Automation (Permitted)**: youkai may move the mouse and press keys via standard OS input APIs (`pynput`) to navigate menus, exactly as a human would. This is *not* memory access, injection, or client modification — the OS delivers the events; the game cannot distinguish them from a physical device. Input is deliberately humanized (Bézier motion, timing jitter) and testing must still use a secondary/alt account per rule 5.

