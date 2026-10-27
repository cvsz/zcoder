<#
.SYNOPSIS
    Generates and exports a Code Signing Certificate for ZCoder Desktop & CLI standalone builds.

.DESCRIPTION
    Creates an Authenticode-compliant self-signed code-signing certificate (RSA 3072, SHA256)
    with Extended Key Usage (EKU) for Code Signing (1.3.6.1.5.5.7.3.3).
    Supports exporting public certificate (.cer) and PKCS#12 bundle (.pfx) with password protection
    and optional auto-importing to LocalMachine / CurrentUser Trusted Root & Trusted Publishers stores.

.PARAMETER Subject
    Certificate Subject Distinguished Name. Default: "CN=ZEAZDEV COMPANY LIMITED, O=ZEAZDEV COMPANY LIMITED, C=TH"

.PARAMETER OutDir
    Output directory to store exported certificates. Default: current directory (".")

.PARAMETER ValidYears
    Validity period in years. Default: 3

.PARAMETER ExportPfx
    Whether to export private key to a .pfx bundle. Default: $false

.PARAMETER PfxPassword
    Password for the .pfx certificate. Reads from $env:ZCODER_PFX_PASSWORD if omitted.

.PARAMETER InstallToTrustStore
    Import public cert into Root & TrustedPublisher stores (requires Admin elevation for LocalMachine). Default: $false

.EXAMPLE
    .\scripts\make_cert.ps1 -OutDir ".\certs" -ExportPfx -InstallToTrustStore
#>

[CmdletBinding()]
param(
    [string]$Subject = "CN=ZEAZDEV COMPANY LIMITED, O=ZEAZDEV COMPANY LIMITED, C=TH",
    [string]$OutDir = ".",
    [int]$ValidYears = 3,
    [switch]$ExportPfx,
    [string]$PfxPassword = $env:ZCODER_PFX_PASSWORD,
    [switch]$InstallToTrustStore
)

$ErrorActionPreference = "Stop"

if ($ExportPfx -and [string]::IsNullOrWhiteSpace($PfxPassword)) {
    throw "Set ZCODER_PFX_PASSWORD before exporting a PFX. No default password is used."
}

# Ensure output directory exists
if (-not (Test-Path -Path $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}
$OutDir = (Resolve-Path -Path $OutDir).Path

Write-Host "==> Generating Code Signing Certificate for ZCoder Desktop..." -ForegroundColor Cyan
Write-Host "    Subject: $Subject"
Write-Host "    Validity: $ValidYears years"

# Create Self-Signed Certificate with Code Signing EKU
$cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject $Subject `
    -KeyAlgorithm RSA `
    -KeyLength 3072 `
    -HashAlgorithm SHA256 `
    -KeyExportPolicy Exportable `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -NotAfter (Get-Date).AddYears($ValidYears)

$thumbprint = $cert.Thumbprint
$cerFile = Join-Path $OutDir "zcoder-codesign.cer"

# Export public certificate (.cer)
Export-Certificate -Cert $cert -FilePath $cerFile -Force | Out-Null
Write-Host "    [OK] Exported Public Cert: $cerFile" -ForegroundColor Green

# Optional: Export PKCS#12 bundle (.pfx)
if ($ExportPfx) {
    $pfxFile = Join-Path $OutDir "zcoder-codesign.pfx"
    $secPass = ConvertTo-SecureString -String $PfxPassword -AsPlainText -Force
    Export-PfxCertificate -Cert $cert -FilePath $pfxFile -Password $secPass -Force | Out-Null
    Write-Host "    [OK] Exported PFX Bundle: $pfxFile" -ForegroundColor Green
}

# Optional: Install to local machine / current user trust stores
if ($InstallToTrustStore) {
    Write-Host "==> Installing public certificate to CurrentUser Trusted Root & Trusted Publishers..." -ForegroundColor Cyan
    Import-Certificate -FilePath $cerFile -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null
    Import-Certificate -FilePath $cerFile -CertStoreLocation "Cert:\CurrentUser\TrustedPublisher" | Out-Null
    Write-Host "    [OK] Certificate trusted for Authenticode on current user account." -ForegroundColor Green
}

Write-Host "`nCertificate Details:" -ForegroundColor Yellow
Write-Host "  Subject:    $($cert.Subject)"
Write-Host "  Thumbprint: $thumbprint"
Write-Host "  Store:      Cert:\CurrentUser\My"
Write-Host "`nTo use with sign_exe.ps1 or build environments:" -ForegroundColor Yellow
Write-Host "  `$env:ZCODER_CERT_THUMBPRINT = `"$thumbprint`""
Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\sign_exe.ps1 -SearchPath .\dist"
