# Ilim Halkasi - LAN erisimi icin 8765 portu inbound kurali
# Kullanim: Dosyaya sag tikla > "Run with PowerShell" > UAC onayina Yes de.
# Acilan pencereyi kapatmak icin Enter'a bas.

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Host 'Yonetici yetkisi isteniyor, UAC penceresini onayla...'
  Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
  exit
}

$ruleName = 'Ilim Halkasi 8765'
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) {
  Write-Host "Kural zaten var: $ruleName"
} else {
  New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow | Out-Null
  Write-Host "Kural eklendi: $ruleName"
}

$matching = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($matching -and $matching.Enabled) {
  Write-Host 'HAZIR: Telefon ayni Wi-Fi''deyken http://192.168.0.107:8765 adresine erisebilir.'
} else {
  Write-Host 'Kural eklenemedi. Yonetici PowerShell''de komutu elle calistir.'
}
Read-Host -Prompt 'Kapatmak icin Enter basin'
