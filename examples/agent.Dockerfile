# An agent image for `gauntlet loop` with the Docker backend. Build it, then point your policy at it:
#   docker build -t gauntlet-agent -f examples/agent.Dockerfile .
#   docker_image_agent = "gauntlet-agent"      (in ~/.config/gauntlet/policy.toml)
# It needs your coding agent plus the toolchain your project's tests use. Python projects: uv is enough.
FROM node:22-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /usr/local/bin/
RUN npm install --global @anthropic-ai/claude-code
