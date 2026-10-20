#Requires -Version 7.0
param(
    [string]$Base = 'http://127.0.0.1:18082',
    [string]$AdminUser = 'demo_20261011',
    [string]$AdminPass = ''
)

$ErrorActionPreference = 'Stop'
if (-not $AdminPass) {
    $secure = Read-Host -AsSecureString "Password for $AdminUser"
    $AdminPass = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    )
}

$stamp = Get-Date -Format 'HHmmss'
$testPass = 'verify-pass-123'
$staffFin = "verify_staff_fin_$stamp"
$staffSales = "verify_staff_sales_$stamp"
$managerFin = "verify_manager_fin_$stamp"
$auditorFin = "verify_auditor_fin_$stamp"
$docPrefix = "verify-$stamp"
$script:results = @()

function Req {
    param(
        [string]$Method,
        [string]$Path,
        [string]$Token,
        $Body = $null,
        $Form = $null
    )
    $params = @{
        Uri = "$Base$Path"
        Method = $Method
        SkipHttpErrorCheck = $true
        TimeoutSec = 120
    }
    if ($Token) { $params.Headers = @{ Authorization = "Bearer $Token" } }
    if ($null -ne $Body) {
        $params.ContentType = 'application/json'
        $params.Body = ($Body | ConvertTo-Json -Depth 8 -Compress)
    }
    if ($null -ne $Form) { $params.Form = $Form }
    $response = Invoke-WebRequest @params
    $json = $null
    try { $json = $response.Content | ConvertFrom-Json } catch { }
    [pscustomobject]@{ Status = [int]$response.StatusCode; Json = $json }
}

function Login([string]$User, [string]$Pass) {
    $r = Req POST '/api/v1/login' $null @{ username = $User; password = $Pass }
    if ($r.Status -ne 200) { throw "login failed for $User (status $($r.Status))" }
    $r.Json.token
}

function Check([string]$Name, [bool]$Passed, [string]$Detail = '') {
    $script:results += [pscustomobject]@{ Check = $Name; Pass = $Passed; Detail = $Detail }
}

function EnsureUser([string]$Token, [string]$User, [string]$Role, [string]$Department) {
    $r = Req POST '/api/v1/users' $Token @{
        username = $User
        password = $testPass
        role = $Role
        department = $Department
    }
    if ($r.Status -notin @(200, 400)) {
        throw "create user $User failed (status $($r.Status))"
    }
}

function UploadDoc([string]$Token, [string]$Name, [string]$Classification, [string]$Department) {
    $path = Join-Path $env:TEMP $Name
    Set-Content -LiteralPath $path -Value "# verify`n`nvalue 1" -Encoding utf8
    Req POST '/api/v1/upload' $Token $null @{
        file = Get-Item -LiteralPath $path
        classification = $Classification
        department = $Department
    }
}

function CatalogNames([string]$Token) {
    $r = Req GET '/api/v1/documents/catalog' $Token
    if ($r.Status -ne 200 -or $null -eq $r.Json.documents) { return @() }
    @($r.Json.documents | ForEach-Object { [string]$_.filename })
}

$adminToken = Login $AdminUser $AdminPass

try {
    EnsureUser $adminToken $staffFin 'staff' '财务部'
    EnsureUser $adminToken $staffSales 'staff' '销售部'
    EnsureUser $adminToken $managerFin 'manager' '财务部'
    EnsureUser $adminToken $auditorFin 'auditor' '财务部'

    $finToken = Login $staffFin $testPass
    $salesToken = Login $staffSales $testPass
    $managerToken = Login $managerFin $testPass
    $auditorToken = Login $auditorFin $testPass

    $level1 = "$docPrefix-level1.md"
    $level2 = "$docPrefix-level2.md"
    $level3 = "$docPrefix-level3.md"
    $ownerDoc = "$docPrefix-owner.md"

    Check 'admin uploads level 1' ((UploadDoc $adminToken $level1 '1' '财务部').Status -eq 200) $level1
    Check 'admin uploads level 2' ((UploadDoc $adminToken $level2 '2' '财务部').Status -eq 200) $level2
    Check 'admin uploads level 3' ((UploadDoc $adminToken $level3 '3' '财务部').Status -eq 200) $level3

    $finCatalog = CatalogNames $finToken
    $salesCatalog = CatalogNames $salesToken
    $managerCatalog = CatalogNames $managerToken
    $auditorCatalog = CatalogNames $auditorToken

    Check 'staff in finance sees level 1' ($finCatalog -contains $level1)
    Check 'staff in finance cannot see level 2' (-not ($finCatalog -contains $level2))
    Check 'staff in finance cannot see level 3' (-not ($finCatalog -contains $level3))
    Check 'staff in sales cannot see finance level 1' (-not ($salesCatalog -contains $level1))
    Check 'manager sees level 2' ($managerCatalog -contains $level2)
    Check 'manager cannot see level 3' (-not ($managerCatalog -contains $level3))
    Check 'auditor sees level 3' ($auditorCatalog -contains $level3)

    $finDownload = Req GET "/api/v1/documents/$level1/file" $finToken
    $salesDownload = Req GET "/api/v1/documents/$level1/file" $salesToken
    Check 'staff can download authorized level 1' ($finDownload.Status -eq 200) "status=$($finDownload.Status)"
    Check 'cross-department download is denied' ($salesDownload.Status -eq 403) "status=$($salesDownload.Status)"

    $badLevel = UploadDoc $finToken "$docPrefix-bad-level.md" '4' '财务部'
    Check 'upload level 4 is refused' ($badLevel.Status -eq 400 -and $badLevel.Json.detail -eq 'invalid_classification') "status=$($badLevel.Status)"
    $badDept = UploadDoc $finToken "$docPrefix-bad-dept.md" '1' '销售部'
    Check 'forged department is refused' ($badDept.Status -eq 403 -and $badDept.Json.detail -eq 'department_override_denied') "status=$($badDept.Status)"

    $ownerUpload = UploadDoc $finToken $ownerDoc '1' '财务部'
    Check 'staff uploads own level 1 document' ($ownerUpload.Status -eq 200) "status=$($ownerUpload.Status)"
    $move = Req PUT '/api/v1/users/department' $adminToken @{ username = $staffFin; department = '销售部' }
    Check 'admin moves the uploader to another department' ($move.Status -eq 200) "status=$($move.Status)"
    $ownerDownload = Req GET "/api/v1/documents/$ownerDoc/file" $finToken
    Check 'owner cannot bypass department after transfer' ($ownerDownload.Status -eq 403 -and $ownerDownload.Json.detail -eq 'department_scope_denied') "status=$($ownerDownload.Status) detail=$($ownerDownload.Json.detail)"

    $roleChange = Req PUT '/api/v1/users/role' $adminToken @{ username = $staffFin; role = 'manager' }
    Check 'admin changes role to manager' ($roleChange.Status -eq 200 -and $roleChange.Json.clearance -eq 2) "status=$($roleChange.Status) clearance=$($roleChange.Json.clearance)"
    $profile = Req GET '/api/v1/profile' $finToken
    Check 'same token sees the new role on next request' ($profile.Status -eq 200 -and $profile.Json.profile.role -eq 'manager' -and $profile.Json.profile.clearance -eq 2) "role=$($profile.Json.profile.role) clearance=$($profile.Json.profile.clearance)"
}
finally {
    if ($adminToken) {
        [void](Req PUT '/api/v1/users/role' $adminToken @{ username = $staffFin; role = 'staff' })
        [void](Req PUT '/api/v1/users/department' $adminToken @{ username = $staffFin; department = '财务部' })
    }
}

$script:results | Format-Table -AutoSize
$failed = @($script:results | Where-Object { -not $_.Pass })
"passed=$($script:results.Count - $failed.Count) failed=$($failed.Count) total=$($script:results.Count)"
if ($failed.Count -gt 0) { exit 1 }
