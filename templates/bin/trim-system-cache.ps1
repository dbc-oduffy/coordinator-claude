# Run from an ELEVATED PowerShell. Trims the system file-cache working set to standby
# (counted as Available), without purging standby or touching process working sets.
# The cache refills if jobs keep reading files; re-run as needed.
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class SysCache {
  [StructLayout(LayoutKind.Sequential)] struct LUID { public uint Lo; public int Hi; }
  [StructLayout(LayoutKind.Sequential)] struct TP { public int Count; public LUID Luid; public int Attr; }
  [DllImport("advapi32.dll", SetLastError=true)] static extern bool OpenProcessToken(IntPtr h, int acc, out IntPtr tok);
  [DllImport("advapi32.dll", SetLastError=true)] static extern bool LookupPrivilegeValue(string s, string n, out LUID l);
  [DllImport("advapi32.dll", SetLastError=true)] static extern bool AdjustTokenPrivileges(IntPtr t, bool d, ref TP n, int l, IntPtr p, IntPtr r);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool SetSystemFileCacheSize(IntPtr min, IntPtr max, int flags);
  [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
  public static string Trim() {
    IntPtr tok;
    if (!OpenProcessToken(GetCurrentProcess(), 0x28, out tok))
      return "failed: OpenProcessToken error " + Marshal.GetLastWin32Error();
    TP tp = new TP(); tp.Count = 1; tp.Attr = 2;
    if (!LookupPrivilegeValue(null, "SeIncreaseQuotaPrivilege", out tp.Luid))
      return "failed: LookupPrivilegeValue error " + Marshal.GetLastWin32Error();
    // Trap: AdjustTokenPrivileges returns true even when the privilege was NOT granted; only
    // GetLastError == ERROR_NOT_ALL_ASSIGNED (1300) says so.
    bool adjusted = AdjustTokenPrivileges(tok, false, ref tp, 0, IntPtr.Zero, IntPtr.Zero);
    int err = Marshal.GetLastWin32Error();
    if (!adjusted || err == 1300)
      return "failed: SeIncreaseQuotaPrivilege not granted, error " + err;
    bool ok = SetSystemFileCacheSize(new IntPtr(-1), new IntPtr(-1), 0);
    return ok ? "trimmed" : ("failed: SetSystemFileCacheSize error " + Marshal.GetLastWin32Error());
  }
}
'@
# Get-Counter paths are localized on non-English hosts; the CIM class and property names are not.
$before = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
[SysCache]::Trim()
Start-Sleep 2
$after = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
"system cache {0:N1} -> {1:N1} GB; available {2:N1} -> {3:N1} GB" -f ($before.SystemCacheResidentBytes/1GB),($after.SystemCacheResidentBytes/1GB),($before.AvailableMBytes/1KB),($after.AvailableMBytes/1KB)
