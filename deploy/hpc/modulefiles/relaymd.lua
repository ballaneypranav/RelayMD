help([[
RelayMD HPC deployment tools and CLI.
Sets install/data roots and adds RelayMD wrappers plus relaymd CLI to PATH.
]])

whatis("Name: relaymd")
whatis("Category: orchestration")
whatis("Description: RelayMD HPC service wrappers and CLI")

local service_root = "/depot/plow/apps/relaymd"
local data_root = "/depot/plow/data/pballane/relaymd-service"
local current_bin = pathJoin(service_root, "bin")

setenv("RELAYMD_SERVICE_ROOT", service_root)
setenv("RELAYMD_DATA_ROOT", data_root)
setenv("RELAYMD_CLI", pathJoin(current_bin, "relaymd"))
prepend_path("PATH", current_bin)
