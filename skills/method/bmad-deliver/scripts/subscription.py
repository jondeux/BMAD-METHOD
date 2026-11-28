"""Fail closed before dispatching through an owner-owned subscription."""

import hashlib
import json
import os
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path

PREFLIGHT_TIMEOUT = 6
MAX_RESPONSE_BYTES = 1024 * 1024
HOSTS = ("codex", "claude")
PAUSE_STATUS = "subscription-paused"
PAUSE_REASONS = {
    "plan-only-unconfirmed": "Confirm plan-only use and available included allowance.",
    "auth-unavailable": "The selected host did not confirm an eligible signed-in subscription.",
    "account-changed": "Confirm plan-only usage for the subscription currently signed in.",
    "alternate-credentials": "The selected host reported an alternate credential or provider.",
    "allowance-unknown": "The selected host could not verify included allowance and paid continuation settings.",
    "allowance-exhausted": "The selected host reported that included allowance is exhausted.",
    "paid-continuation-possible": "The selected host reported spendable or unlimited credits.",
}
BINDING_FIELDS = ("run_id", "attempt", "intake_revision", "phase", "subscription_host")
CODEX_PLANS = (
    "go",
    "plus",
    "pro",
    "prolite",
    "team",
    "self_serve_business_prolite",
    "business",
    "ent26",
    "enterprise",
    "edu",
    "edu_plus",
    "edu_pro",
)
CLAUDE_PLANS = ("pro", "max", "ultra", "team", "enterprise")
CODEX_LIMITS = (
    "rate_limit_reached",
    "workspace_owner_credits_depleted",
    "workspace_member_credits_depleted",
    "workspace_owner_usage_limit_reached",
    "workspace_member_usage_limit_reached",
)
BASE_ENV = ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")
CLAUDE_OVERRIDES = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_CUSTOM_HEADERS",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR",
    "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR",
    "CLAUDE_CODE_OAUTH_REFRESH_TOKEN",
    "ANTHROPIC_PROFILE",
    "ANTHROPIC_FEDERATION_RULE_ID",
    "ANTHROPIC_ORGANIZATION_ID",
    "ANTHROPIC_WORKSPACE_ID",
    "CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST",
    "CLAUDE_CODE_USE_ANTHROPIC_AWS",
    "CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_FOUNDRY",
    "CLAUDE_CODE_USE_MANTLE",
    "CLAUDE_CODE_USE_VERTEX",
)


def safe_environment(host):
    config_home = "CODEX_HOME" if host == "codex" else "CLAUDE_CONFIG_DIR"
    return {key: os.environ[key] for key in (*BASE_ENV, config_home) if key in os.environ}


def codex_options():
    """Pin first-party endpoints and preserve the existing credential storage backend."""
    options = [
        "-c",
        'model_provider="openai"',
        "-c",
        'chatgpt_base_url="https://chatgpt.com/backend-api/"',
        "-c",
        'openai_base_url="https://chatgpt.com/backend-api/codex"',
        "-c",
        "model_providers={}",
        "-c",
        "mcp_servers={}",
        "-c",
        "features.hooks=false",
        "-c",
        "features.apps=false",
        "-c",
        "features.multi_agent=false",
        "-c",
        'web_search="disabled"',
    ]
    config = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"
    try:
        with config.open("rb") as source:
            store = tomllib.load(source).get("cli_auth_credentials_store")
    except FileNotFoundError:
        store = None
    if store is not None:
        if store not in ("auto", "file", "keyring", "ephemeral"):
            raise ValueError("unrecognized Codex credential store")
        options.extend(("-c", f'cli_auth_credentials_store="{store}"'))
    return options


def codex_auth_reason(result):
    account = result.get("account")
    if not isinstance(account, dict):
        return "auth-unavailable"
    if account.get("type") in ("apiKey", "amazonBedrock") or result.get("requiresOpenaiAuth") is False:
        return "alternate-credentials"
    if (
        account.get("type") != "chatgpt"
        or account.get("planType") not in CODEX_PLANS
        or result.get("requiresOpenaiAuth") is not True
    ):
        return "auth-unavailable"
    return None


def codex_allowance_reason(result):
    allowed = result.get("ordinaryUsageAllowed")
    legacy = result.get("rateLimits")
    by_limit = result.get("rateLimitsByLimitId")
    if allowed is False:
        return "allowance-exhausted"
    if allowed is not True or not isinstance(legacy, dict) or (by_limit is not None and not isinstance(by_limit, dict)):
        return "allowance-unknown"

    snapshots = [legacy, *(by_limit or {}).values()]
    base = (by_limit or {}).get("codex")
    found_window = False
    no_credits = False
    for index, snapshot in enumerate(snapshots):
        if not isinstance(snapshot, dict):
            return "allowance-unknown"
        is_base = index == 0 or snapshot is base
        reached = snapshot.get("rateLimitReachedType")
        if reached in CODEX_LIMITS or snapshot.get("spendControlReached") is True:
            return "allowance-exhausted"
        if reached is not None:
            return "allowance-unknown"
        credits = snapshot.get("credits")
        if credits is not None:
            if not isinstance(credits, dict):
                return "allowance-unknown"
            has_credits, unlimited = credits.get("hasCredits"), credits.get("unlimited")
            if has_credits is True or unlimited is True:
                return "paid-continuation-possible"
            if has_credits is not False or unlimited is not False:
                return "allowance-unknown"
            if is_base:
                no_credits = True
        for key in ("primary", "secondary"):
            window = snapshot.get(key)
            if window is None:
                continue
            percentage = window.get("usedPercent") if isinstance(window, dict) else None
            if type(percentage) is not int or percentage < 0:
                return "allowance-unknown"
            if percentage >= 100:
                return "allowance-exhausted"
            if is_base:
                found_window = True
    return None if found_window and no_credits else "allowance-unknown"


def account_fingerprint(*fields):
    if not all(isinstance(field, str) and field.strip() for field in fields):
        return None
    return hashlib.sha256(json.dumps(fields).encode()).hexdigest()


def codex_preflight(executable):
    """Use only the account RPCs on a private stdio connection, without token refresh."""
    with tempfile.TemporaryDirectory(prefix="bmad-subscription-") as directory:
        proc = subprocess.Popen(
            [executable, *codex_options(), "app-server", "--listen", "stdio://"],
            cwd=directory,
            env=safe_environment("codex"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            with selectors.DefaultSelector() as reader:
                reader.register(proc.stdout, selectors.EVENT_READ)
                deadline = time.monotonic() + PREFLIGHT_TIMEOUT
                buffered = b""

                def send(method, *, request_id=None, params=None):
                    packet = {"method": method}
                    if request_id is not None:
                        packet["id"] = request_id
                    if params is not None:
                        packet["params"] = params
                    proc.stdin.write(json.dumps(packet).encode() + b"\n")
                    proc.stdin.flush()

                def receive(request_id):
                    nonlocal buffered
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError
                        line, separator, rest = buffered.partition(b"\n")
                        if separator:
                            buffered = rest
                            message = json.loads(line)
                            if not isinstance(message, dict):
                                raise ValueError("invalid account response")
                            if message.get("id") == request_id and "method" not in message:
                                result = message.get("result")
                                if "error" in message or not isinstance(result, dict):
                                    raise ValueError("account response unavailable")
                                return result
                            continue
                        if not reader.select(remaining):
                            raise TimeoutError
                        chunk = os.read(proc.stdout.fileno(), 65536)
                        if not chunk or len(buffered) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise ValueError("account response unavailable")
                        buffered += chunk

                send("initialize", request_id=1, params={"clientInfo": {"name": "bmad-delivery", "version": "1"}})
                receive(1)
                send("initialized", params={})
                send("account/read", request_id=2, params={"refreshToken": False})
                auth = receive(2)
                reason = codex_auth_reason(auth)
                if reason:
                    return reason, None
                send("account/rateLimits/read", request_id=3)
                rates = receive(3)
                identity = account_fingerprint("codex", rates.get("accountId"), auth["account"]["planType"])
                return codex_allowance_reason(rates) or (None if identity else "auth-unavailable"), identity
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            proc.stdin.close()
            proc.stdout.close()


def claude_preflight():
    if any(os.environ.get(key) for key in CLAUDE_OVERRIDES):
        return "alternate-credentials", None
    executable = shutil.which("claude")
    if not executable:
        return "auth-unavailable", None
    result = subprocess.run(
        [executable, "auth", "status", "--json"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=PREFLIGHT_TIMEOUT,
        env=safe_environment("claude"),
    )
    if len(result.stdout) > MAX_RESPONSE_BYTES:
        return "auth-unavailable", None
    account = json.loads(result.stdout)
    if not isinstance(account, dict):
        return "auth-unavailable", None
    if (
        account.get("apiKeySource")
        or account.get("apiProvider") not in (None, "firstParty")
        or account.get("authMethod") not in (None, "none", "claude.ai")
    ):
        return "alternate-credentials", None
    if (
        result.returncode
        or account.get("loggedIn") is not True
        or account.get("apiProvider") != "firstParty"
        or account.get("authMethod") != "claude.ai"
        or account.get("subscriptionType") not in CLAUDE_PLANS
    ):
        return "auth-unavailable", None
    # The serving workspace also checks /status and /usage for each model stage.
    identity = account_fingerprint("claude", account.get("orgId"), account.get("email"), account["subscriptionType"])
    return (None if identity else "auth-unavailable"), identity


def preflight(host, *, confirmed, allowance, codex=None):
    if not confirmed:
        return "plan-only-unconfirmed", None
    if allowance != "available":
        return ("allowance-exhausted" if allowance == "exhausted" else "allowance-unknown"), None
    if host == "codex" and (not codex or not shutil.which(codex)):
        return "auth-unavailable", None
    try:
        return codex_preflight(codex) if host == "codex" else claude_preflight()
    except (OSError, ValueError, subprocess.SubprocessError):
        return ("allowance-unknown" if host == "codex" else "auth-unavailable"), None


def pause_receipt(job, reason):
    if job.get("subscription_host") not in HOSTS or reason not in PAUSE_REASONS:
        raise ValueError("invalid subscription pause")
    return {"status": PAUSE_STATUS, "reason": reason, **{field: job[field] for field in BINDING_FIELDS}}


def validate_pause(result, job):
    reason = result.get("reason")
    if (
        not isinstance(reason, str)
        or type(result.get("attempt")) is not int
        or type(result.get("intake_revision")) is not int
        or result != pause_receipt(job, reason)
    ):
        raise ValueError("invalid subscription pause receipt")
    return reason
