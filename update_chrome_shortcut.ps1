$Shell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$ShortcutPaths = @(
    "$DesktopPath\Google Chrome.lnk",
    "$env:PUBLIC\Desktop\Google Chrome.lnk",
    "$env:APPDATA\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\Google Chrome.lnk"
)

$updated = $false
foreach ($Path in $ShortcutPaths) {
    if (Test-Path $Path) {
        $Shortcut = $Shell.CreateShortcut($Path)
        # Preserve original target, but add argument
        $Shortcut.Arguments = "--remote-debugging-port=9222"
        $Shortcut.Save()
        Write-Host "Successfully updated shortcut at: $Path"
        $updated = $true
    }
}

if (-not $updated) {
    Write-Host "No standard Chrome shortcut was found. You can add '--remote-debugging-port=9222' to your Chrome shortcut arguments manually."
}
