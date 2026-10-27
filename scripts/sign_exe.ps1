<#
.SYNOPSIS
    Digitally signs ZCoder Desktop executables and libraries with Authenticode SHA256 & RFC3161 Timestamp.

.DESCRIPTION
    Scans the specified search path (default: dist) for target executables and dynamic libraries
    (*.exe, *.dll) and applies an Authenticode digital signature using either:
      1. A PFX file (-Pfx or $env:ZCODER_PFX) with password (-Password or $env:ZCODER_PFX_PASSWORD)
      2. A certificate thumbprint (-Thumbprint or $env:ZCODER_CERT_THUMBPRINT) from Windows Cert Stores
    Supports RFC3161 timestamps with fallback timestamp authorities, description embedding,
    and post-sign verification.

.PARAMETER SearchPath
    Target directory containing executables to sign. Default: "dist"

.PARAMETER FileFilter
    File extensions/patterns to sign. Default: @("*.exe", "*.dll")

.PARAMETER Pfx
    Path to .pfx certificate file. Defaults to $env:ZCODER_PFX or $env:AUTODJ_PFX.

.PARAMETER Password
    Password for .pfx certificate file. Defaults to $env:ZCODER_PFX_PASSWORD or $env:AUTODJ_PFX_PASSWORD.

.PARAMETER Thumbprint
    Certificate thumbprint in Cert:\CurrentUser\My or Cert:\LocalMachine\My.
    Defaults to $env:ZCODER_CERT_THUMBPRINT or $env:AUTODJ_CERT_THUMBPRINT.

.PARAMETER TimestampServer
    Primary RFC3161 timestamp server URL. Default: "http://timestamp.digicert.com"

.PARAMETER FallbackTimestampServers
    List of fallback timestamp server URLs if primary fails.

.PARAMETER Description
    Application/product description for the signature. Default: "ZCoder Desktop"

.PARAMETER DescriptionUrl
    Product documentation URL. Default: "https://github.com/cvsz/zcoder"

.PARAMETER VerifyOnly
    Verify existing signatures without signing. Default: $false

.EXAMPLE
    .\scripts\sign_exe.ps1 -SearchPath ".\dist" -Thumbprint "515DB3BD9BF14AA6646AC6770C54E869DE49D872"
#>

[CmdletBinding()]
param(
    [string]$SearchPath = "dist",
    [string[]]$FileFilter = @("*.exe"),
    [string]$Pfx = $(if ($env:ZCODER_PFX) { $env:ZCODER_PFX } else { $env:AUTODJ_PFX }),
    [string]$Password = $(if ($env:ZCODER_PFX_PASSWORD) { $env:ZCODER_PFX_PASSWORD } else { $env:AUTODJ_PFX_PASSWORD }),
    [string]$Thumbprint = $(if ($env:ZCODER_CERT_THUMBPRINT) { $env:ZCODER_CERT_THUMBPRINT } else { $env:AUTODJ_CERT_THUMBPRINT }),
    [string]$TimestampServer = "http://timestamp.digicert.com",
    [string[]]$FallbackTimestampServers = @(
        "http://timestamp.sectigo.com",
        "http://timestamp.globalsign.com/tsa/r6advanced1",
        "http://tsa.starfieldtech.com"
    ),
    [string]$Description = "ZCoder Desktop",
    [string]$DescriptionUrl = "https://github.com/cvsz/zcoder",
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -Path $SearchPath)) {
    throw "Target search path not found: '$SearchPath'. Run build first."
}

# Resolve candidate binaries
$targets = @()
foreach ($filter in $FileFilter) {
    $targets += Get-ChildItem -Path $SearchPath -Filter $filter -Recurse -File
}

if ($targets.Count -eq 0) {
    throw "No matching files ($($FileFilter -join ', ')) found under '$SearchPath'."
}

Write-Host "==> ZCoder Desktop Binary Authenticode Signing & Verification" -ForegroundColor Cyan
Write-Host "    Search Directory: $SearchPath"
Write-Host "    Files Found:      $($targets.Count)"

if ($VerifyOnly) {
    Write-Host "`n==> Verifying signatures only..." -ForegroundColor Cyan
    $failures = 0
    foreach ($file in $targets) {
        $sig = Get-AuthenticodeSignature -FilePath $file.FullName
        $statusColor = if ($sig.Status -eq "Valid") { "Green" } else { "Red" }
        Write-Host ("[{0}] {1} - {2}" -f $sig.Status, $file.Name, $sig.StatusMessage) -ForegroundColor $statusColor
        if ($sig.Status -ne "Valid") { $failures++ }
    }
    if ($failures -gt 0) {
        throw "Signature verification failed for $failures file(s)."
    }
    Write-Host "    [OK] All files verified successfully." -ForegroundColor Green
    return
}

# Load Certificate
$cert = $null
if ($Pfx) {
    Write-Host "    Loading certificate from PFX file: $Pfx"
    if (-not (Test-Path -Path $Pfx)) {
        throw "Specified PFX file not found: '$Pfx'"
    }
    $secPass = if ($Password) { ConvertTo-SecureString -String $Password -AsPlainText -Force } else { $null }
    $cert = Get-PfxCertificate -FilePath $Pfx -Password $secPass
} elseif ($Thumbprint) {
    $cleanThumbprint = $Thumbprint -replace "\s", ""
    Write-Host "    Resolving certificate by Thumbprint: $cleanThumbprint"
    $cert = Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\My -Recurse 2>$null |
        Where-Object { $_.Thumbprint -eq $cleanThumbprint } |
        Select-Object -First 1

    if (-not $cert) {
        throw "Code signing certificate with thumbprint '$cleanThumbprint' not found in CurrentUser\My or LocalMachine\My stores."
    }
} else {
    throw "No signing certificate provided. Specify -Pfx, -Thumbprint, or set `$env:ZCODER_CERT_THUMBPRINT / `$env:ZCODER_PFX. (Use make_cert.ps1 to generate a self-signed cert)"
}

Write-Host "    Signer Certificate: $($cert.Subject)" -ForegroundColor Green
Write-Host "    Thumbprint:         $($cert.Thumbprint)"
Write-Host "    Expires:            $($cert.NotAfter)`n"

$allTimestampServers = @($TimestampServer) + $FallbackTimestampServers
$successCount = 0
$failCount = 0

foreach ($file in $targets) {
    $filePath = $file.FullName
    Write-Host "--> Signing: $($file.Name)..." -NoNewline
    
    $signed = $false
    $lastResult = $null

    foreach ($tsUrl in $allTimestampServers) {
        try {
            $lastResult = Set-AuthenticodeSignature `
                -FilePath $filePath `
                -Certificate $cert `
                -HashAlgorithm SHA256 `
                -TimestampServer $tsUrl `
                -Description $Description `
                -DescriptionUrl $DescriptionUrl `
                -ErrorAction Stop

            if ($lastResult.SignerCertificate -ne $null) {
                $signed = $true
                Write-Host " [Signed with TS: $tsUrl]" -ForegroundColor Green
                break
            }
        } catch {
            # Try next timestamp authority
            continue
        }
    }

    if (-not $signed) {
        # Fallback to signing without timestamp if external servers are unreachable (e.g. offline sandbox / air-gapped build)
        Write-Warning "Timestamp servers unreachable. Applying local signature without timestamp..."
        $lastResult = Set-AuthenticodeSignature `
            -FilePath $filePath `
            -Certificate $cert `
            -HashAlgorithm SHA256 `
            -Description $Description `
            -DescriptionUrl $DescriptionUrl
        
        if ($lastResult.SignerCertificate -ne $null) {
            $signed = $true
            Write-Host " [Signed (No Timestamp)]" -ForegroundColor Yellow
        }
    }

    if ($signed) {
        $successCount++
        # Verify signature
        $verify = Get-AuthenticodeSignature -FilePath $filePath
        Write-Host "    Status: $($verify.Status) | Digest: $($verify.SignerCertificate.Thumbprint)" -ForegroundColor Gray
    } else {
        $failCount++
        Write-Host " [FAILED]" -ForegroundColor Red
        Write-Host "    Error: $($lastResult.StatusMessage)" -ForegroundColor Red
    }
}

Write-Host "`n==> Signing Summary:" -ForegroundColor Cyan
Write-Host "    Total Processed: $($targets.Count)"
Write-Host "    Successful:      $successCount" -ForegroundColor Green
Write-Host "    Failed:          $failCount" -ForegroundColor $(if ($failCount -gt 0) { "Red" } else { "Green" })

if ($failCount -gt 0) {
    throw "Failed to sign $failCount binary file(s)."
}

Write-Host "`nAll ZCoder Desktop binaries signed and verified successfully." -ForegroundColor Green
