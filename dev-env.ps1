# dev-env.ps1 — source this in any new terminal: . .\dev-env.ps1
$env:FIRESTORE_EMULATOR_HOST = "localhost:8080"
$env:FIREBASE_AUTH_EMULATOR_HOST = "localhost:9099"
$env:GOOGLE_CLOUD_PROJECT = "keluarga-embah-yasin"
Write-Host "Emulator env vars set" -ForegroundColor Green