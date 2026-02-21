FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates gnupg && \
    # Node.js (required by Claude Agent SDK's bundled CLI)
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get update && apt-get install -y nodejs && \
    # GitHub CLI
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && apt-get install -y gh && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p state logs && \
    # Create non-root user (Claude Code CLI refuses --dangerously-skip-permissions as root)
    useradd -m -s /bin/bash botuser && \
    chown -R botuser:botuser /app

USER botuser

# /repo is mounted at runtime as root-owned; mark it safe for botuser's git
RUN git config --global --add safe.directory /repo

CMD ["python", "main.py"]
