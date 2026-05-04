# Tuesday operator runbook — WSL + OpenFOAM v2312 setup

Run-once steps to prepare the workstation for the Phase BA campaign.
Should take ~30 min wall-clock end-to-end (most of it apt downloads).

## 1. Install WSL2 + Ubuntu 22.04

In an **elevated PowerShell**:

```powershell
wsl --install -d Ubuntu-22.04
```

Reboots. After reboot, Ubuntu launches and prompts for a username +
password. Pick anything; you won't need it across the WSL boundary
(the orchestrator drives WSL non-interactively).

Verify after reboot:

```powershell
wsl --list --verbose
```

Should show `Ubuntu-22.04   Running   2`.

## 2. Install OpenFOAM v2312 inside WSL

In a **WSL terminal** (`wsl` from PowerShell, or "Ubuntu-22.04" Start menu):

```bash
sudo sh -c "wget -O - https://dl.openfoam.com/add-debian-repo.sh | bash"
sudo apt-get update
sudo apt-get install -y openfoam2312-default
echo "source /usr/lib/openfoam/openfoam2312/etc/bashrc" >> ~/.bashrc
source ~/.bashrc
```

Verify:

```bash
which simpleFoam
simpleFoam -help | head -1
```

Should print the binary path and the v2312 banner.

## 3. Mount the Windows-side repo into WSL

The repo lives at `C:\Users\ignac\OneDrive\Desktop\WFLW`. WSL2
auto-mounts Windows drives at `/mnt/c/`, `/mnt/d/`, etc. Quick
sanity check:

```bash
ls /mnt/c/Users/ignac/OneDrive/Desktop/WFLW/cfd/los_pelambres/template/
```

Should show `0/`, `constant/`, `system/`, `Allmesh`, `Allrun`.

**Important**: OneDrive sync can interfere with file timestamps that
OpenFOAM relies on. If you see weird "file already exists" errors
during `snappyHexMesh`, move the run directory off OneDrive:

```bash
mkdir -p /mnt/d/openfoam-runs/los_pelambres/
# Then run the orchestrator with --runs-dir /mnt/d/openfoam-runs/los_pelambres/
```

The repo's `cfd/los_pelambres/runs/` is `.gitignore`d, so it doesn't
have to live inside the repo.

## 4. Download SRTM tiles

From any browser, grab the four tiles covering Los Pelambres:

* `S32W071.hgt`
* `S32W072.hgt`
* `S33W071.hgt`
* `S33W072.hgt`

Source: <https://dwtkns.com/srtm30m/> (no auth) or USGS Earth
Explorer (auth required, but more authoritative).

Drop them into `cfd/los_pelambres/dem/` (which is gitignored).

## 5. Build the STL surface

From the **Windows-side** (PowerShell or VSCode terminal — pure-
Python script, no OpenFOAM dependency):

```powershell
.venv\Scripts\python.exe scripts\cfd\dem_to_stl.py `
    --tiles cfd\los_pelambres\dem\*.hgt `
    --bbox -71.0,-32.0,-70.5,-31.5 `
    --out cfd\los_pelambres\template\constant\triSurface\terrain.stl
```

Should print mosaic shape, cropped shape, and triangle count.

## 6. Dry-run the campaign

```powershell
.venv\Scripts\python.exe scripts\cfd\run_campaign.py `
    --regime-grid 16x3 --dry-run
```

Stages 48 run directories under `cfd\los_pelambres\runs\` (or the
`--runs-dir` override) with patched BCs. No OpenFOAM invocation.

## 7. Execute the campaign

```powershell
.venv\Scripts\python.exe scripts\cfd\run_campaign.py `
    --regime-grid 16x3 --execute
```

Approx 60-72 h serial on the 5900X. Each regime writes
`results.json` + `log.simpleFoam` to its run directory. Monitor:

```powershell
type cfd\los_pelambres\runs\dir045_speed02_neutral\log.simpleFoam | Select-Object -Last 30
```

## 8. Reduce to dispersion matrix

After the campaign completes:

```powershell
.venv\Scripts\python.exe scripts\cfd\reduce_to_matrix.py `
    --runs-dir cfd\los_pelambres\runs\ `
    --mine-id los-pelambres `
    --out cfd\los_pelambres\reduced\dispersion_matrix.json
```

(Entry point shipped in BA.5.)

## 9. Persist and promote

Restart the FastAPI app; the lifespan hook (BA.10) will detect the
new matrix, run the calibration probe (BA.7), and promote
`cfd_lookup_v0.1.0` over the `distance_decay_baseline` if the probe
passes.
