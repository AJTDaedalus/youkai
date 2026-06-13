#[cfg(windows)]
pub fn is_admin() -> bool {
    unsafe { windows::Win32::UI::Shell::IsUserAnAdmin().into() }
}

#[cfg(not(windows))]
pub fn is_admin() -> bool {
    true
}
