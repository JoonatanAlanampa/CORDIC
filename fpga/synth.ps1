# synth.ps1 - build the CORDIC-1 verification bitstream for the ULX3S 85F.
#   powershell -File fpga\synth.ps1
# Output: fpga\build\cordic_ulx3s.bit
# Flash:  openFPGALoader -b ulx3s fpga\build\cordic_ulx3s.bit
# Needs the OSS CAD Suite in ~\opt\oss-cad-suite (same as the CPU project).
$ErrorActionPreference = "Stop"
$oss = "$env:USERPROFILE\opt\oss-cad-suite"
$env:PATH = "$oss\bin;$oss\lib;" + $env:PATH
# work with relative paths from the repo root: the user profile path
# contains a space, which yosys' script parser will not forgive
Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Force fpga\build | Out-Null

yosys -q -p "read_verilog -sv src/project.sv src/cordic.sv fpga/ulx3s_top.sv; synth_ecp5 -top ulx3s_top -json fpga/build/cordic.json"
if ($LASTEXITCODE -ne 0) { throw "yosys failed" }

nextpnr-ecp5 --85k --package CABGA381 --json fpga/build/cordic.json `
    --lpf fpga/ulx3s.lpf --textcfg fpga/build/cordic.config
if ($LASTEXITCODE -ne 0) { throw "nextpnr failed" }

ecppack fpga/build/cordic.config fpga/build/cordic_ulx3s.bit
if ($LASTEXITCODE -ne 0) { throw "ecppack failed" }

Write-Output "OK: fpga\build\cordic_ulx3s.bit"
