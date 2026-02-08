# =============================================================================
# ProcureWatch — Phase 0 : Hygiène Git
# Exécuter dans PowerShell à la racine du projet
# =============================================================================

# --- 0.1 : Remplacer .gitignore ---
Write-Host "`n=== 0.1 : Mise à jour .gitignore ===" -ForegroundColor Cyan

$gitignoreContent = @"
# Python
__pycache__/
*.py[cod]
*`$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
venv/
env/
ENV/
.venv/

# Environment variables
.env
.env.local
.env.backup

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/

# Alembic
alembic/versions/*.pyc

# OS
.DS_Store
Thumbs.db

# Data files
data/raw/
data/_cache/
data/*.db
!data/.gitkeep
data/publicprocurement_*.json
data/debug/

# Logs
logs/
*.log

# Local DB files
*.db
*.db.bak

# Local browser profile (SECURITY: contains cookies, sessions, cache)
.pw-profile/

# Node modules (frontend deps - install via npm install)
web/node_modules/
node_modules/

# Local browser / cookie artifacts
cookies.txt

# Misc artifacts
0
"@

Set-Content -Path ".gitignore" -Value $gitignoreContent -Encoding UTF8
Write-Host "  .gitignore mis à jour" -ForegroundColor Green


# --- 0.2 : Fixer requirements.txt (UTF-8 sans BOM) ---
Write-Host "`n=== 0.2 : Fix requirements.txt (UTF-16LE -> UTF-8) ===" -ForegroundColor Cyan

$reqContent = Get-Content -Path "requirements.txt" -Encoding Unicode | 
    Where-Object { $_.Trim() -ne "" }
# Écrire en UTF-8 sans BOM
[System.IO.File]::WriteAllLines(
    (Join-Path $PWD "requirements.txt"),
    $reqContent,
    [System.Text.UTF8Encoding]::new($false)
)
Write-Host "  requirements.txt converti en UTF-8 (sans BOM)" -ForegroundColor Green


# --- 0.3 : Supprimer fichiers sensibles/inutiles du tracking git ---
Write-Host "`n=== 0.3 : Nettoyage du tracking git ===" -ForegroundColor Cyan

# Supprimer du tracking (pas du disque)
$toUntrack = @(
    ".pw-profile/",
    "web/node_modules/",
    ".env.backup",
    "dev.db",
    "dev.db.bak",
    "0"
)

foreach ($path in $toUntrack) {
    $fullPath = Join-Path $PWD $path
    if (Test-Path $fullPath) {
        git rm -r --cached $path 2>$null
        Write-Host "  Untracked: $path" -ForegroundColor Yellow
    } else {
        Write-Host "  Skip (not found): $path" -ForegroundColor DarkGray
    }
}


# --- 0.4 : Vérification ---
Write-Host "`n=== Vérification ===" -ForegroundColor Cyan

# Vérifier encodage
$bytes = [System.IO.File]::ReadAllBytes((Join-Path $PWD "requirements.txt"))
if ($bytes[0] -eq 0x61) {  # 'a' de 'alembic'
    Write-Host "  requirements.txt : UTF-8 OK" -ForegroundColor Green
} else {
    Write-Host "  requirements.txt : ATTENTION encodage suspect (premier byte: $($bytes[0]))" -ForegroundColor Red
}

# Vérifier .gitignore
$gi = Get-Content ".gitignore" -Raw
if ($gi -match "\.pw-profile/" -and $gi -match "\.env\.backup") {
    Write-Host "  .gitignore : contient les nouvelles exclusions" -ForegroundColor Green
} else {
    Write-Host "  .gitignore : ATTENTION, vérifier manuellement" -ForegroundColor Red
}

# Montrer le status git
Write-Host "`n=== Git Status ===" -ForegroundColor Cyan
git status --short


# --- Instructions finales ---
Write-Host "`n=== Actions manuelles requises ===" -ForegroundColor Magenta
Write-Host @"

1. VÉRIFIER le git status ci-dessus
2. COMMITTER :
   git add -A
   git commit -m "chore: phase 0 - git hygiene, fix encoding, remove secrets"

3. PUSHER vers les deux remotes :
   git push origin main
   git push railway main

4. SÉCURITÉ - Tes credentials BOSA étaient dans .env.backup commité !
   -> Considère les comme compromis
   -> Contacte BOSA pour renouveler :
      - INT client_secret: 93fd5d95-...
      - PR client_secret: 22487941-...
   -> Après renouvellement, mettre à jour .env local + Railway env vars

"@ -ForegroundColor Yellow
