help([[
RelayMD HPC deployment tools and CLI.
Sets default service paths and adds RelayMD wrappers plus relaymd CLI to PATH.
]])

whatis("Name: relaymd")
whatis("Category: orchestration")
whatis("Description: RelayMD HPC service wrappers and CLI")

local service_root = "/depot/plow/apps/relaymd"
local data_root = "/depot/plow/data/pballane/relaymd-service"
local current_bin = pathJoin(service_root, "bin")

setenv("RELAYMD_SERVICE_ROOT", service_root)
setenv("RELAYMD_DATA_ROOT", data_root)
setenv("RELAYMD_CONFIG", pathJoin(data_root, "config", "relaymd-config.yaml"))
setenv("RELAYMD_ENV_FILE", pathJoin(data_root, "config", "relaymd-service.env"))
setenv("RELAYMD_STATUS_FILE", pathJoin(data_root, "state", "relaymd-service.status"))
setenv("RELAYMD_BIND_PATHS", data_root .. ":" .. data_root)
setenv("RELAYMD_CLI", pathJoin(current_bin, "relaymd"))
prepend_path("PATH", current_bin)
