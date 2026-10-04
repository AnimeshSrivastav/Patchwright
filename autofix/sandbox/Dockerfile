FROM python:3.12-slim

# Non-root user for all generated code execution
RUN useradd -m -s /bin/sh nobody_user && \
    mkdir -p /workspace && \
    chown nobody_user:nobody_user /workspace

# Install pytest (only dependency allowed in sandbox)
RUN pip install --no-cache-dir pytest==8.0.0

# No network access (set via --network=none in docker_runner.py)
# No host mounts (enforced in docker_runner.py)
# Read-only filesystem where possible (except /workspace)

WORKDIR /workspace
USER nobody_user

CMD ["sleep", "infinity"]
